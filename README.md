# Smart Queue & Appointment Management System

A complete Flask demo project for digital token generation, appointment booking, live queue tracking, and admin queue control.

## Features
- Book an appointment and receive a digital token
- Sequential daily token generation (Q001, Q002, ...)
- Track token status, live queue position, people ahead, and estimated wait
- Admin dashboard to call next, start service, complete, skip, or cancel tokens
- Service selection with average service time
- Auto-refreshing public queue board
- SQLite database created automatically (easy demo setup)
- MySQL migration notes included below

## Run on Windows PowerShell
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```
Then open: http://127.0.0.1:5000

Admin page: http://127.0.0.1:5000/admin/login  
Default admin password: `admin123`

## Database
The demo uses SQLite (`queue.db`) so it runs immediately without installing a database server.

## Main Queue Logic
- FIFO by booking time/token number for active tokens.
- Each day has its own sequence: Q001, Q002, ...
- Estimated wait = people ahead × selected service's average service time.

## Demo Flow
1. Open the home page.
2. Book two or three appointments.
3. Show generated tokens.
4. Open the public queue board in another tab.
5. Login to Admin (`admin123`).
6. Click **Call Next**, then **Start**, then **Complete**.
7. Show that the public board and tracking page update.
