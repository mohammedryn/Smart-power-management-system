@echo off
echo Starting Server... > startup_log.txt
python server.py >> startup_log.txt 2>&1
echo Done. >> startup_log.txt
