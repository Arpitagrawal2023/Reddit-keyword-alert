import schedule
import time
from reddit_monitor import check_reddit


print("🤖 Reddit Keyword Alert Bot v2.0 Started!")


# Schedule: Check every 2 minutes (gives enough time to process 1000 posts + 1000 comments)
schedule.every(2).minutes.do(check_reddit)

# Run once immediately on startup
print("Running initial check...")
check_reddit()

print("Scheduled checks will run every 2 minutes...")

# Then run on schedule
while True:
    schedule.run_pending()
    time.sleep(1)  # Check every second if a job needs to run
