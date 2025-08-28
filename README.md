# Intellidollar 💵
*A self-hosted budget tracking web app by Intellidwell*

Intellidollar helps you take control of your finances with:
- ✅ Simple budget creation (monthly or one-time)  
- ✅ Category-based transaction tracking  
- ✅ Beautiful progress bars to visualize spending vs. budget  
- ✅ Quick-add transactions (mobile friendly)  
- ✅ Income tracking and analytics  

---

## 🚀 Quick Start

1. Create a new folder for your Intellidollar instance:
   ```bash
   mkdir intellidollar && cd intellidollar
Save the following as docker-compose.yml:
(Insert your Docker Compose script here)

Start the stack:

bash
Copy code
docker compose up -d
Open your browser at http://localhost:8000 🎉

⚙️ Configuration
SECRET_KEY
Set this to a long, random string to keep sessions secure.

DATABASE_URL
Follows SQLAlchemy format. Example for MySQL:

bash
Copy code
mysql+pymysql://username:password@db/budgetdb
Ports
The app listens on port 8000 internally. Change the left side of the ports mapping if you want a different external port. Example:

makefile
Copy code
ports:
  - "5000:8000"
🧪 Quick Test with SQLite (no MySQL)
If you just want to try Intellidollar without MySQL, you can run:

bash
Copy code
docker run -it --rm -p 8000:8000 \
  -e FLASK_ENV=production \
  -e SECRET_KEY=changeme123 \
  -e DATABASE_URL=sqlite:///budget.db \
  --name intellidollar_web \
  tanner23456/intellidollar-web:latest
This will create a budget.db file inside the container. For persistence, you’d mount a volume.

📸 Screenshots
(Coming soon – show off your dashboard & analytics!)

📝 License
This project is licensed under the MIT License.

yaml
Copy code

---
