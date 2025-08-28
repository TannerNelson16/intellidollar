# intellidollar 💵
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
   ```
Save the following as docker-compose.yml:
```yaml
services:
  web:
    image: tanner23456/intellidollar:latest
    container_name: intellidollar_web
    ports:
      - "8000:8000"
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=changeme123          # 🔑 replace with your own secure key
      - DATABASE_URL=mysql+pymysql://intelliuser:intellipass@db/budgetdb
    depends_on:
      - db

  db:
    image: mysql:8
    container_name: intellidollar_db
    restart: always
    environment:
      - MYSQL_ROOT_PASSWORD=changemeRoot # 🔑 replace this
      - MYSQL_DATABASE=budgetdb
      - MYSQL_USER=intelliuser
      - MYSQL_PASSWORD=intellipass
    volumes:
      - db_data:/var/lib/mysql

volumes:
  db_data:
```

Start the stack:

```bash
docker compose up -d
```
Open your browser at http://localhost:8000 🎉

## ⚙️ Configuration
SECRET_KEY
Set this to a long, random string to keep sessions secure.

##DATABASE_URL
Follows SQLAlchemy format. Example for MySQL:

```bash
mysql+pymysql://username:password@db/budgetdb
```
## Ports
The app listens on port 8000 internally. Change the left side of the ports mapping if you want a different external port. Example:
```yaml
ports:
  - "5000:8000"
```

## 📸 Screenshots
(Coming soon !)

## Mobile
Mobile app in the works!

## 📝 License
This project is licensed under the MIT License.

