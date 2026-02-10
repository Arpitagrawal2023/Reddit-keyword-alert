import os
import json
import requests
import resend
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()

# Set Resend API key
resend.api_key = os.getenv("RESEND_API_KEY")

REDDIT_POSTS_URL = "https://www.reddit.com/r/all/new.json?limit=100"
REDDIT_COMMENTS_URL = "https://www.reddit.com/r/all/comments.json?limit=100"
HEADERS = {
    "User-Agent": "reddit-keyword-alert-bot/2.0"
}

# Load keywords from JSON
with open("keywords.json", "r") as f:
    KEYWORDS = json.load(f)["keywords"]

# Track seen posts and comments to avoid duplicates
SEEN_POSTS_FILE = "seen_posts.json"
SEEN_COMMENTS_FILE = "seen_comments.json"

def load_seen_items(filename):
    """Load previously seen item IDs from file"""
    if os.path.exists(filename):
        with open(filename, "r") as f:
            return set(json.load(f))
    return set()

def save_seen_items(seen_items, filename):
    """Save seen item IDs to file (keep only last 5000 to prevent file bloat)"""
    seen_list = list(seen_items)
    if len(seen_list) > 5000:
        seen_list = seen_list[-5000:]
    with open(filename, "w") as f:
        json.dump(seen_list, f)

def send_email(matches):
    """Send email with keyword matches"""
    if not matches:
        return
    
    html = "<h2>🚨 Reddit Keyword Matches Found!</h2>"
    html += f"<p>Found <strong>{len(matches)}</strong> new item(s) matching your keywords:</p>"
    html += "<hr>"
    
    for match in matches:
        item_type = "💬 Comment" if match['type'] == 'comment' else "📝 Post"
        
        html += f"""
        <div style="margin: 20px 0; padding: 15px; border-left: 3px solid #FF4500; background-color: #f8f9fa;">
            <p style="margin: 0 0 10px 0;">
                <strong style="color: #FF4500;">Keywords:</strong> {match['keywords']}
            </p>
            <p style="margin: 0 0 10px 0;">
                <strong>Type:</strong> {item_type}
            </p>
            <p style="margin: 0 0 10px 0;">
                <strong>Title:</strong> <a href="{match['url']}" style="color: #0079D3; text-decoration: none;">{match['title']}</a>
            </p>
            <p style="margin: 0; font-size: 0.9em; color: #666;">
                Subreddit: r/{match['subreddit']} | Posted: {match['created']}
            </p>
        </div>
        """
    
    html += "<hr>"
    html += "<p style='color: #666; font-size: 0.85em; margin-top: 20px;'>This is an automated alert from your Reddit Keyword Monitor.</p>"

    try:
        resend.Emails.send({
            "from": "Reddit Alert <notifications@mail.chromateo.com>",
            "to": ["arpitjindal1511@gmail.com"],
            "subject": f"🚨 Reddit Alert: {len(matches)} new match(es) for your keywords",
            "html": html
        })
        print(f"✅ Email sent successfully with {len(matches)} match(es)!")
        return True
    except Exception as e:
        print(f"❌ Error sending email: {e}")
        return False

def fetch_multiple_batches(url, num_batches=10):
    """Fetch multiple batches of posts/comments using pagination"""
    all_items = []
    after = None
    
    for batch_num in range(num_batches):
        try:
            # Build URL with pagination
            batch_url = url
            if after:
                batch_url += f"&after={after}"
            
            # Make request
            response = requests.get(batch_url, headers=HEADERS, timeout=10)
            response.raise_for_status()
            data = response.json()
            
            # Get items from this batch
            items = data["data"]["children"]
            all_items.extend(items)
            
            # Get pagination token for next batch
            after = data["data"].get("after")
            
            print(f"  Batch {batch_num + 1}/{num_batches}: Fetched {len(items)} items (after={after})")
            
            # If no more items, stop
            if not after or len(items) == 0:
                print(f"  No more items available, stopping at batch {batch_num + 1}")
                break
                
        except Exception as e:
            print(f"  ❌ Error fetching batch {batch_num + 1}: {e}")
            break
    
    return all_items

def process_items(items, seen_items, item_type="post"):
    """Process posts or comments and find keyword matches"""
    matches = []
    new_items_checked = 0
    
    for item in items:
        item_data = item["data"]
        item_id = item_data.get("id")
        
        # Skip if we've already seen this item
        if item_id in seen_items:
            continue
        
        new_items_checked += 1
        
        # Get item details
        title = item_data.get("title", "")
        body = item_data.get("selftext", "") if item_type == "post" else item_data.get("body", "")
        subreddit = item_data.get("subreddit", "unknown")
        permalink = item_data.get("permalink", "")
        created = datetime.fromtimestamp(item_data.get("created_utc", 0)).strftime('%Y-%m-%d %H:%M:%S')
        
        # For comments, we need to get the post title separately
        if item_type == "comment":
            # Use link_title if available, otherwise use a snippet of the comment
            title = item_data.get("link_title", f"Comment: {body[:50]}...")
        
        # Combine title and body for searching
        content = f"{title} {body}".lower()
        
        # Check for keyword matches
        matched_keywords = set()
        for keyword in KEYWORDS:
            if keyword.lower() in content:
                matched_keywords.add(keyword)
        
        # If any keywords matched, add to matches
        if matched_keywords:
            matches.append({
                "keywords": ", ".join(matched_keywords),
                "title": title,
                "url": "https://reddit.com" + permalink,
                "subreddit": subreddit,
                "created": created,
                "type": item_type
            })
        
        # Mark item as seen
        seen_items.add(item_id)
    
    return matches, new_items_checked

def check_reddit():
    """Main function to check Reddit for keyword matches"""
    print("\n" + "=" * 60)
    print(f"🔍 Checking Reddit... ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})")
    print("=" * 60)
    
    # Load seen items
    seen_posts = load_seen_items(SEEN_POSTS_FILE)
    seen_comments = load_seen_items(SEEN_COMMENTS_FILE)
    
    all_matches = []
    
    # ===== CHECK POSTS =====
    print("\n📝 Fetching POSTS (10 batches of 100 = up to 1,000 posts)...")
    posts = fetch_multiple_batches(REDDIT_POSTS_URL, num_batches=10)
    print(f"✅ Total posts fetched: {len(posts)}")
    
    post_matches, new_posts_checked = process_items(posts, seen_posts, item_type="post")
    all_matches.extend(post_matches)
    
    print(f"📊 Checked {new_posts_checked} new post(s)")
    print(f"✨ Found {len(post_matches)} post match(es)")
    
    # ===== CHECK COMMENTS =====
    print("\n💬 Fetching COMMENTS (10 batches of 100 = up to 1,000 comments)...")
    comments = fetch_multiple_batches(REDDIT_COMMENTS_URL, num_batches=10)
    print(f"✅ Total comments fetched: {len(comments)}")
    
    comment_matches, new_comments_checked = process_items(comments, seen_comments, item_type="comment")
    all_matches.extend(comment_matches)
    
    print(f"📊 Checked {new_comments_checked} new comment(s)")
    print(f"✨ Found {len(comment_matches)} comment match(es)")
    
    # ===== SUMMARY =====
    print("\n" + "=" * 60)
    print(f"🎯 Keywords monitoring: {', '.join(KEYWORDS)}")
    print(f"📊 Total new items checked: {new_posts_checked + new_comments_checked}")
    print(f"✨ Total matches found: {len(all_matches)}")
    print("=" * 60)
    
    # Send email if there are matches
    if all_matches:
        send_email(all_matches)
    else:
        print("ℹ️  No keyword matches found.")
    
    # Save updated seen items (with size limit to prevent file bloat)
    save_seen_items(seen_posts, SEEN_POSTS_FILE)
    save_seen_items(seen_comments, SEEN_COMMENTS_FILE)
    
    print("\n✅ Check complete!\n")
