@echo off
:: Finance Data Lake — Auto Startup Script
:: รันอัตโนมัติเมื่อเปิดเครื่อง ผ่าน Windows Task Scheduler
:: Manual: double-click ไฟล์นี้เพื่อรัน

set PROJECT=D:\_Work_Workspace\03_Data_Projects\_Finance_Data_Lake
set PYTHON=C:\Users\surasit.k\AppData\Local\Programs\Python\Python313\Scripts\uvicorn

echo.
echo  Finance Data Lake — Starting API...
echo  Path : %PROJECT%
echo  Port : 8000
echo  Docs : http://localhost:8000/docs
echo.

cd /d "%PROJECT%"
"%PYTHON%" backend.main:app --reload --port 8000 --host 127.0.0.1
