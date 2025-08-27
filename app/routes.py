from datetime import date
from decimal import Decimal
from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import select, func, and_, or_, case
from .models import User, Category, Transaction, Budget, SavingsStart
from .forms import (
    RegisterForm,
    LoginForm,
    TransactionForm,
    BudgetForm,
    CategoryForm,
    SavingsStartForm,
)
from .utils import current_month_str
import re

bp = Blueprint("core", __name__)

# -------------------- helpers --------------------


def normalize_month(m: str | None) -> str | None:
    """
    Normalize many representations into 'YYYY-MM':
      - 'YYYY-M'
      - 'YYYY-MM'
      - 'YYYY-MM-DD' (or anything starting with YYYY-MM)
    Returns None if blank/None.
    """
    if m is None:
        return None
    m = str(m).strip()
    if not m:
        return None

    # If it starts with YYYY-MM, chop to first 7 chars
    if re.match(r"^\d{4}-\d{2}", m):
        return m[:7]

    parts = m.split("-")
    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
        y = int(parts[0])
        mm = int(parts[1])
        return f"{y:04d}-{mm:02d}"
    return m  # fallback (unusual formats)

def make_months_options(start_from: str = "2025-07", months_back: int = 1, months_ahead: int = 12):
    """
    Build a list of YYYY-MM strings from max(start_from, (today - months_back))
    up through (today + months_ahead), inclusive.
    """
    today = date.today()
    cur = f"{today.year:04d}-{today.month:02d}"

    # compute (today - months_back) as YYYY-MM
    y, m = today.year, today.month
    idx = (y * 12 + (m - 1)) - months_back
    back_y, back_m = divmod(idx, 12)
    back_m += 1
    back = f"{back_y:04d}-{back_m:02d}"

    # start is the later of start_from and back
    start = max(start_from, back)

    # compute (today + months_ahead)
    idx_end = (y * 12 + (m - 1)) + months_ahead
    end_y, end_m = divmod(idx_end, 12)
    end_m += 1
    end = f"{end_y:04d}-{end_m:02d}"

    # iterate months from start to end (inclusive)
    def next_month(ym: str) -> str:
        yy, mm = int(ym[:4]), int(ym[5:7])
        mm += 1
        if mm == 13:
            yy += 1
            mm = 1
        return f"{yy:04d}-{mm:02d}"

    months = []
    cur_ym = start
    while cur_ym <= end:
        months.append(cur_ym)
        cur_ym = next_month(cur_ym)
    return months

def applicable_budgets_by_category(db, user_id: int, month: str):
    """
    For the given user & month, return a dict:
      { category_id: (Budget, Category) }
    Preference:
      - One-time for the same month wins over recurring
      - Else recurring
    Also: if a one-time budget has a NULL/blank month, treat it as the selected month.
    """
    rows = db.execute(
        select(Budget, Category)
        .join(Category, Budget.category_id == Category.id)
        .where(Budget.user_id == user_id)
    ).all()

    chosen: dict[int, tuple[Budget, Category, int]] = {}
    for b, c in rows:
        b_month_norm = normalize_month(b.month)
        # NEW: if one-time and month is empty, treat as the currently selected month
        assumed_month = b_month_norm or month
        is_one_time_this_month = (b.recurrence != "monthly" and assumed_month == month)
        is_recurring = (b.recurrence == "monthly")

        if not (is_one_time_this_month or is_recurring):
            continue

        score = 2 if is_one_time_this_month else 1
        prev = chosen.get(c.id)
        if not prev or score > prev[2]:
            chosen[c.id] = (b, c, score)

    return {cid: (b, c) for cid, (b, c, _) in chosen.items()}

# -------------------- Auth --------------------

@bp.route("/")
@login_required
def index():
    return redirect(url_for("core.dashboard"))

@bp.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("core.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        db = current_app.db_session
        existing = db.scalar(select(User).where(User.email == form.email.data.lower()))
        if existing:
            flash("Email already registered.", "warning")
            return redirect(url_for("core.login"))

        user = User(email=form.email.data.lower())
        user.set_password(form.password.data)
        db.add(user)
        db.commit()

        default_cat = Category(name="General", icon="tag", user_id=user.id)
        db.add(default_cat)
        db.commit()

        flash("Account created. Please log in.", "success")
        return redirect(url_for("core.login"))
    return render_template("register.html", form=form)

@bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("core.dashboard"))
    form = LoginForm()
    if form.validate_on_submit():
        db = current_app.db_session
        user = db.scalar(select(User).where(User.email == form.email.data.lower()))
        if user and user.check_password(form.password.data):
            login_user(user)
            flash("Welcome back!", "success")
            next_url = request.args.get("next")
            return redirect(next_url or url_for("core.dashboard"))
        flash("Invalid credentials.", "danger")
    return render_template("login.html", form=form)

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    flash("Logged out.", "info")
    return redirect(url_for("core.login"))

# -------------------- Dashboard + Quick Add --------------------

# ---------- Dashboard (net spending + monthly income card) ----------


@bp.route("/dashboard")
@login_required
def dashboard():
    db = current_app.db_session

    # month picker
    month = normalize_month(request.args.get("month") or current_month_str())
    months_options = make_months_options(months_back=12, months_ahead=12)

    # ---------- Budgets effective in this month ----------
    # Monthly budgets always count; one-time count only for matching month
    monthly_rows = db.execute(
        select(Budget, Category)
        .join(Category, Budget.category_id == Category.id)
        .where(and_(Budget.user_id == current_user.id, Budget.recurrence == "monthly"))
    ).all()

    one_time_rows = db.execute(
        select(Budget, Category)
        .join(Category, Budget.category_id == Category.id)
        .where(
            and_(
                Budget.user_id == current_user.id,
                Budget.recurrence != "monthly",
                Budget.month == month,
            )
        )
    ).all()

    # Build effective budget-by-category map (sum in case user sets more than one)
    budget_by_cat: dict[int, Decimal] = {}
    cat_name: dict[int, str] = {}

    for b, c in monthly_rows + one_time_rows:
        cat_name[c.id] = c.name
        budget_by_cat[c.id] = budget_by_cat.get(c.id, Decimal("0")) + Decimal(str(b.amount or 0))

    # ---------- Per-category net spend (expenses minus refunds recorded as income) ----------
    # Sum EXPENSES for the month grouped by category
    exp_rows = db.execute(
        select(
            Transaction.category_id,
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.type == "expense",
                func.date_format(Transaction.date, "%Y-%m") == month,
            )
        ).group_by(Transaction.category_id)
    ).all()
    expenses_by_cat = {cid: Decimal(str(total)) for cid, total in exp_rows}

    # Sum INCOME for the month grouped by category (used as refunds/offsets if same category)
    inc_rows = db.execute(
        select(
            Transaction.category_id,
            func.coalesce(func.sum(Transaction.amount), 0)
        ).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.type == "income",
                func.date_format(Transaction.date, "%Y-%m") == month,
            )
        ).group_by(Transaction.category_id)
    ).all()
    income_by_cat = {cid: Decimal(str(total)) for cid, total in inc_rows}

    # Build dashboard cards for categories that actually have a budget
    cards = []
    for cid, budget_amt in budget_by_cat.items():
        spent_net = expenses_by_cat.get(cid, Decimal("0")) - income_by_cat.get(cid, Decimal("0"))
        if spent_net < 0:
            spent_net = Decimal("0")  # don't go negative on the bar
        pct = float((spent_net / budget_amt) * 100) if budget_amt > 0 else 0.0
        pct = min(pct, 999.0)
        cards.append({
            "category_id": cid,
            "category": cat_name.get(cid, "Unknown"),
            "amount": f"{budget_amt:.2f}",
            "spent": f"{spent_net:.2f}",
            "percent": pct,
        })
    # Sort cards by category name for a stable display
    cards.sort(key=lambda x: x["category"].lower())

    # ---------- Unbudgeted expenses (net) ----------
    # Anything with net spend > 0 in a category that has NO effective budget this month
    unbudgeted_total = Decimal("0")
    for cid, exp_total in expenses_by_cat.items():
        if cid not in budget_by_cat:
            net = exp_total - income_by_cat.get(cid, Decimal("0"))
            if net > 0:
                unbudgeted_total += net
    unbudgeted_spent = f"{unbudgeted_total:.2f}"

    # ---------- Income progress (Income vs Expenses) ----------
    total_income = Decimal(str(sum(income_by_cat.values())))  # month total income
    total_expense = Decimal(str(sum(expenses_by_cat.values())))  # month total expenses
    if total_income > 0:
        income_use_pct = float((total_expense / total_income) * 100)
    else:
        income_use_pct = 0.0
    income_use_pct = min(income_use_pct, 999.0)
    income_over = income_use_pct > 102.0

    income_bar = {
        "income": float(total_income),
        "expenses": float(total_expense),
        "percent": income_use_pct,
        "over": income_over,
    }

    # ---------- Recent transactions ----------
    txns = db.execute(
        select(Transaction, Category)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
        .limit(10)
    ).all()

    # ---------- Quick-add form + categories ----------
    qa_form = TransactionForm()
    cats = db.execute(
        select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).scalars().all()
    qa_form.category_id.choices = [(c.id, c.name) for c in cats]

    return render_template(
        "dashboard.html",
        month=month,
        months_options=months_options,
        cards=cards,
        txns=txns,
        qa_form=qa_form,
        cats=cats,
        unbudgeted_spent=unbudgeted_spent,
        income_bar=income_bar,
        total_income=float(total_income),  # kept for template convenience
    )
# -------------------- Transactions --------------------

@bp.route("/transactions", methods=["GET", "POST"])
@login_required
def transactions():
    db = current_app.db_session
    cats = db.execute(
        select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).scalars().all()

    form = TransactionForm()
    form.category_id.choices = [(c.id, c.name) for c in cats]

    if form.validate_on_submit():
        txn = Transaction(
            user_id=current_user.id,
            category_id=form.category_id.data,
            amount=form.amount.data,
            date=form.date.data,
            description=form.description.data or "",
            type=form.type.data,
        )
        db.add(txn)
        db.commit()
        flash("Transaction saved.", "success")
        referer = request.headers.get("Referer", "")
        if "/dashboard" in referer:
            return redirect(url_for("core.dashboard"))
        return redirect(url_for("core.transactions"))

    q = db.execute(
        select(Transaction, Category)
        .join(Category, Transaction.category_id == Category.id)
        .where(Transaction.user_id == current_user.id)
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    ).all()

    return render_template("transactions.html", form=form, txns=q)

@bp.route("/transactions/edit/<int:txn_id>", methods=["GET", "POST"])
@login_required
def transactions_edit(txn_id: int):
    db = current_app.db_session
    txn = db.get(Transaction, txn_id)
    if not txn or txn.user_id != current_user.id:
        flash("Transaction not found.", "warning")
        return redirect(url_for("core.transactions"))

    cats = db.execute(
        select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).scalars().all()

    form = TransactionForm()
    form.category_id.choices = [(c.id, c.name) for c in cats]

    if request.method == "GET":
        form.type.data = txn.type
        form.category_id.data = txn.category_id
        form.amount.data = txn.amount
        form.date.data = txn.date
        form.description.data = txn.description or ""

    if form.validate_on_submit():
        txn.type = form.type.data
        txn.category_id = form.category_id.data
        txn.amount = form.amount.data
        txn.date = form.date.data
        txn.description = form.description.data or ""
        db.commit()
        flash("Transaction updated.", "success")
        return redirect(url_for("core.transactions"))

    return render_template("transactions_edit.html", form=form)

@bp.route("/transactions/delete/<int:txn_id>", methods=["POST"])
@login_required
def transactions_delete(txn_id: int):
    db = current_app.db_session
    txn = db.get(Transaction, txn_id)
    if not txn or txn.user_id != current_user.id:
        flash("Transaction not found.", "warning")
        return redirect(url_for("core.transactions"))
    db.delete(txn)
    db.commit()
    flash("Transaction deleted.", "info")
    return redirect(url_for("core.transactions"))

# -------------------- Budgets --------------------

# ---- Budgets route (replace your existing budgets() with this) ----
@bp.route("/budgets", methods=["GET", "POST"])
@login_required
def budgets():
    db = current_app.db_session

    # Limit months list: start no earlier than 2025-07, show 1 month back and 12 ahead
    months_options = make_months_options(start_from="2025-07", months_back=1, months_ahead=12)

    cats = db.execute(
        select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).scalars().all()

    form = BudgetForm()
    form.category_id.choices = [(c.id, c.name) for c in cats]

    # Default the form month to the current month on first load
    if request.method == "GET" and not form.month.data:
        form.month.data = current_month_str()

    # When POST comes from the <select name="month">, normalize and push into the form
    if request.method == "POST":
        posted_month = request.form.get("month")  # from the dropdown in budgets.html
        if posted_month:
            form.month.data = normalize_month(posted_month)

    if form.validate_on_submit():
        m_norm = normalize_month(form.month.data or current_month_str())

        existing = db.execute(
            select(Budget).where(
                and_(
                    Budget.user_id == current_user.id,
                    Budget.category_id == form.category_id.data,
                    Budget.month == m_norm,
                )
            )
        ).scalar_one_or_none()

        if existing:
            existing.amount = form.amount.data
            existing.recurrence = form.recurrence.data or "one_time"
            flash("Budget updated.", "info")
        else:
            b = Budget(
                user_id=current_user.id,
                category_id=form.category_id.data,
                month=m_norm,
                amount=form.amount.data,
                recurrence=form.recurrence.data or "one_time",
            )
            db.add(b)
            flash("Budget added.", "success")

        db.commit()
        return redirect(url_for("core.budgets"))

    # Recurring (monthly) budgets: one row per category
    recurring_rows = db.execute(
        select(Budget, Category)
        .join(Category, Budget.category_id == Category.id)
        .where(and_(Budget.user_id == current_user.id, Budget.recurrence == "monthly"))
        .order_by(Category.name)
    ).all()

    # One-time budgets: show with explicit month
    one_time_rows = db.execute(
        select(Budget, Category)
        .join(Category, Budget.category_id == Category.id)
        .where(and_(Budget.user_id == current_user.id, Budget.recurrence != "monthly"))
        .order_by(Budget.month.desc(), Category.name)
    ).all()

    return render_template(
        "budgets.html",
        form=form,
        months_options=months_options,
        recurring_rows=recurring_rows,
        one_time_rows=one_time_rows,
    )

# ---------- Budgets: Edit (robust save) ----------

@bp.route("/budgets/edit/<int:budget_id>", methods=["GET", "POST"])
@login_required
def budgets_edit(budget_id: int):
    db = current_app.db_session
    b = db.get(Budget, budget_id)
    if not b or b.user_id != current_user.id:
        flash("Budget not found.", "warning")
        return redirect(url_for("core.budgets"))

    months_options = make_months_options(start_from="2025-07", months_back=12, months_ahead=12)

    cats = db.execute(
        select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).scalars().all()

    form = BudgetForm()
    form.category_id.choices = [(c.id, c.name) for c in cats]

    if request.method == "GET":
        form.category_id.data = b.category_id
        form.month.data = b.month or current_month_str()
        form.amount.data = b.amount
        form.recurrence.data = b.recurrence or "one_time"

    # Ensure a month value is posted, even if the month input is disabled in the template
    if request.method == "POST":
        posted_month = request.form.get("month") or b.month or current_month_str()
        form.month.data = normalize_month(posted_month)

    if form.validate_on_submit():
        b.category_id = form.category_id.data
        b.amount = form.amount.data
        b.recurrence = form.recurrence.data or "one_time"
        # Only allow changing month for one-time budgets
        if b.recurrence != "monthly":
            b.month = normalize_month(form.month.data or b.month or current_month_str())
        db.commit()
        flash("Budget updated.", "success")
        return redirect(url_for("core.budgets"))

    return render_template(
        "budgets_edit.html",
        form=form,
        months_options=months_options,
        budget=b,
    )

@bp.route("/budgets/delete/<int:budget_id>", methods=["POST"])
@login_required
def budgets_delete(budget_id: int):
    db = current_app.db_session
    b = db.get(Budget, budget_id)
    if not b or b.user_id != current_user.id:
        flash("Budget not found.", "warning")
        return redirect(url_for("core.budgets"))
    db.delete(b)
    db.commit()
    flash("Budget deleted.", "info")
    return redirect(url_for("core.budgets"))

# -------------------- Categories --------------------

@bp.route("/categories", methods=["GET", "POST"])
@login_required
def categories():
    db = current_app.db_session
    form = CategoryForm()
    if form.validate_on_submit():
        exists = db.execute(
            select(Category).where(
                and_(
                    Category.user_id == current_user.id,
                    Category.name == form.name.data.strip(),
                )
            )
        ).scalar_one_or_none()
        if exists:
            flash("Category already exists.", "warning")
        else:
            db.add(
                Category(
                    name=form.name.data.strip(),
                    icon=form.icon.data or "tag",
                    user_id=current_user.id,
                )
            )
            db.commit()
            flash("Category added.", "success")
        return redirect(url_for("core.categories"))

    cats = db.execute(
        select(Category).where(Category.user_id == current_user.id).order_by(Category.name)
    ).scalars().all()
    return render_template("categories.html", form=form, categories=cats)

@bp.route("/categories/edit/<int:cat_id>", methods=["GET", "POST"])
@login_required
def categories_edit(cat_id: int):
    db = current_app.db_session
    cat = db.get(Category, cat_id)
    if not cat or cat.user_id != current_user.id:
        flash("Category not found.", "warning")
        return redirect(url_for("core.categories"))

    form = CategoryForm()
    if request.method == "GET":
        form.name.data = cat.name
        form.icon.data = cat.icon

    if form.validate_on_submit():
        exists = db.execute(
            select(Category).where(
                and_(
                    Category.user_id == current_user.id,
                    Category.name == form.name.data.strip(),
                    Category.id != cat.id,
                )
            )
        ).scalar_one_or_none()
        if exists:
            flash("Another category with that name already exists.", "warning")
        else:
            cat.name = form.name.data.strip()
            cat.icon = form.icon.data or "tag"
            db.commit()
            flash("Category updated.", "success")
            return redirect(url_for("core.categories"))

    return render_template("categories_edit.html", form=form)

@bp.route("/categories/delete/<int:cat_id>", methods=["POST"])
@login_required
def categories_delete(cat_id: int):
    db = current_app.db_session
    cat = db.get(Category, cat_id)
    if not cat or cat.user_id != current_user.id:
        flash("Category not found.", "warning")
        return redirect(url_for("core.categories"))

    tcount = db.scalar(
        select(func.count(Transaction.id)).where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.category_id == cat.id,
            )
        )
    )
    if tcount and tcount > 0:
        flash("Cannot delete: there are transactions in this category.", "warning")
        return redirect(url_for("core.categories"))

    bcount = db.scalar(
        select(func.count(Budget.id)).where(
            and_(Budget.user_id == current_user.id, Budget.category_id == cat.id)
        )
    )
    if bcount and bcount > 0:
        flash("Cannot delete: there are budgets for this category.", "warning")
        return redirect(url_for("core.categories"))

    db.delete(cat)
    db.commit()
    flash("Category deleted.", "info")
    return redirect(url_for("core.categories"))

# -------------------- Analytics --------------------

@bp.route("/analytics", methods=["GET", "POST"])
@login_required
def analytics():
    db = current_app.db_session
    form = SavingsStartForm()
    if form.validate_on_submit():
        s = db.execute(
            select(SavingsStart).where(
                and_(
                    SavingsStart.user_id == current_user.id,
                    SavingsStart.month == normalize_month(form.month.data),
                )
            )
        ).scalar_one_or_none()
        if s:
            s.amount = form.amount.data
            flash("Starting savings updated.", "info")
        else:
            s = SavingsStart(
                user_id=current_user.id,
                month=normalize_month(form.month.data),
                amount=form.amount.data,
            )
            db.add(s)
            flash("Starting savings set.", "success")
        db.commit()
        return redirect(url_for("core.analytics"))

    rows = db.execute(
        select(
            func.date_format(Transaction.date, "%Y-%m").label("m"),
            func.sum(case((Transaction.type == "income", Transaction.amount), else_=0)).label("inc"),
            func.sum(case((Transaction.type == "expense", Transaction.amount), else_=0)).label("exp"),
        )
        .where(Transaction.user_id == current_user.id)
        .group_by("m")
        .order_by("m")
    ).all()

    months = [r[0] for r in rows]
    income = [float(r[1] or 0) for r in rows]
    expenses = [float(r[2] or 0) for r in rows]

    one_time_rows = db.execute(
        select(Budget.month, func.sum(Budget.amount))
        .where(and_(Budget.user_id == current_user.id, Budget.recurrence != "monthly"))
        .group_by(Budget.month)
    ).all()
    one_time_map = {normalize_month(m): float(total or 0) for m, total in one_time_rows}

    recurring_total = db.scalar(
        select(func.coalesce(func.sum(Budget.amount), 0)).where(
            and_(Budget.user_id == current_user.id, Budget.recurrence == "monthly")
        )
    )
    recurring_total = float(recurring_total or 0)

    budgeted = []
    for m in months:
        base = one_time_map.get(m, 0.0) + recurring_total
        budgeted.append(round(base, 2))

    seeds = {
        normalize_month(s.month): float(s.amount)
        for s in db.execute(
            select(SavingsStart).where(SavingsStart.user_id == current_user.id)
        ).scalars()
    }
    savings = []
    running = 0.0
    for i, m in enumerate(months):
        if m in seeds:
            running = seeds[m]
        running += (income[i] - expenses[i])
        savings.append(round(running, 2))

    return render_template(
        "analytics.html",
        form=form,
        months=months,
        income=income,
        expenses=expenses,
        budgeted=budgeted,
        savings=savings,
    )

# -------------------- Category & Unbudgeted views --------------------

@bp.route("/categories/<int:cat_id>/transactions")
@login_required
def category_transactions(cat_id: int):
    db = current_app.db_session
    month = normalize_month(request.args.get("month")) or current_month_str()
    cat = db.get(Category, cat_id)
    if not cat or cat.user_id != current_user.id:
        flash("Category not found.", "warning")
        return redirect(url_for("core.dashboard"))

    txns = db.execute(
        select(Transaction)
        .where(
            and_(
                Transaction.user_id == current_user.id,
                Transaction.category_id == cat.id,
                func.date_format(Transaction.date, "%Y-%m") == month,
            )
        )
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    ).scalars().all()

    total_expense = sum(float(t.amount) for t in txns if t.type == "expense")
    total_income = sum(float(t.amount) for t in txns if t.type == "income")

    return render_template(
        "category_transactions.html",
        category=cat,
        month=month,
        txns=txns,
        total_expense=total_expense,
        total_income=total_income,
    )

@bp.route("/unbudgeted/transactions")
@login_required
def unbudgeted_transactions():
    db = current_app.db_session
    month = normalize_month(request.args.get("month")) or current_month_str()

    by_cat = applicable_budgets_by_category(db, current_user.id, month)
    budgeted_cat_ids = set(by_cat.keys())

    filters = [
        Transaction.user_id == current_user.id,
        Transaction.type == "expense",
        func.date_format(Transaction.date, "%Y-%m") == month,
    ]
    if budgeted_cat_ids:
        filters.append(~Transaction.category_id.in_(budgeted_cat_ids))

    txns = db.execute(
        select(Transaction, Category)
        .join(Category, Transaction.category_id == Category.id)
        .where(and_(*filters))
        .order_by(Transaction.date.desc(), Transaction.id.desc())
    ).all()

    total_unbudgeted = sum(float(t.amount) for t, _ in txns)

    return render_template(
        "unbudgeted_transactions.html",
        month=month,
        txns=txns,
        total_unbudgeted=total_unbudgeted,
    )

