import mysql.connector
import time
import random
from datetime import datetime


def connect_db():
    try:
        db = mysql.connector.connect(
            host="trolley.proxy.rlwy.net",
            port=41829,
            user="root",
            password="pskpxuaQLNOcrvaXVwzKvAfmtWOSfwQc",
            database="railway"
        )
        print("✅ Backend Connected to Database")
        return db
    except Exception as e:
        print("❌ Database Connection Failed:", e)
        exit()


db = connect_db()
cursor = db.cursor(buffered=True)

current_green = 1
cycle_start = time.time()

print("🚦 Smart Traffic Backend Started — updating every 3 seconds...")
print("   Press Ctrl+C to stop.\n")

try:
    while True:

        # ── Get signals ──
        cursor.execute("SELECT signal_id FROM signals ORDER BY signal_id")
        signals = [row[0] for row in cursor.fetchall()]

        if not signals:
            print("No signals in DB. Check your tables.")
            time.sleep(5)
            continue

        # ── Emergency check ──
        cursor.execute("SELECT signal_id FROM signal_timing WHERE green_time = 999")
        emg = cursor.fetchone()

        if emg:
            new_emg = emg[0]
            if new_emg != current_green:
                current_green = new_emg
                print(f"🚑 EMERGENCY OVERRIDE — Signal {current_green}")
                cursor.execute("""
                    INSERT INTO emergency_log (signal_id, event_type)
                    VALUES (%s, 'TRIGGERED')
                """, (current_green,))

        # ── Update vehicle count ──
        for sid in signals:
            cursor.execute(
                "SELECT vehicle_count FROM traffic_data WHERE signal_id=%s", (sid,)
            )
            row = cursor.fetchone()
            v = row[0] if row else 20

            if sid == current_green:
                v = max(5, v - random.randint(12, 25))
            else:
                v = min(v + random.randint(3, 12), 100)

            cursor.execute(
                "UPDATE traffic_data SET vehicle_count=%s, timestamp=NOW() WHERE signal_id=%s",
                (v, sid)
            )

        # ── Adaptive signal timing + countdown ──
        for sid in signals:
            cursor.execute(
                "SELECT vehicle_count FROM traffic_data WHERE signal_id=%s", (sid,)
            )
            v = cursor.fetchone()[0]

            cursor.execute(
                "SELECT green_time FROM signal_timing WHERE signal_id=%s", (sid,)
            )
            gt = cursor.fetchone()[0] or 0

            # Don't overwrite emergency flag
            if gt == 999:
                continue

            if sid == current_green:
                if gt <= 0:
                    # Reset green time based on vehicle count
                    if v > 70:   gtime = 65
                    elif v > 40: gtime = 45
                    elif v > 20: gtime = 30
                    else:        gtime = 20
                else:
                    # Count down by 3 each tick
                    gtime = max(0, gt - 3)
            else:
                gtime = 0

            cursor.execute(
                "UPDATE signal_timing SET green_time=%s WHERE signal_id=%s",
                (gtime, sid)
            )

        db.commit()

        # ── Log ──
        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Green: S{current_green} | Cycle: {int(time.time()-cycle_start)}s")

        # ── Signal switching ──
        if time.time() - cycle_start > 35 and (not emg):
            # Log emergency cleared if any
            cursor.execute("""
                UPDATE emergency_log
                SET cleared_at=NOW(), duration_sec=TIMESTAMPDIFF(SECOND, triggered_at, NOW())
                WHERE signal_id=%s AND cleared_at IS NULL
            """, (current_green,))
            db.commit()

            current_green = (current_green % len(signals)) + 1
            cycle_start = time.time()
            print(f"↩ Switched green to S{current_green}")

        time.sleep(3)

except KeyboardInterrupt:
    print("\n🛑 Backend stopped.")
except Exception as e:
    print(f"❌ Error: {e}")
finally:
    if db:
        db.close()
        print("DB connection closed.")