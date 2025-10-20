# sort_GPT: A Summarizer and Organizer for GPT Convos

sort_GPT automatically converts your ChatGPT data export into organized Markdown files, adds summaries and tags via OpenAI’s API, and builds an interactive searchable dashboard in Obsidian.

- Idiot-proof installation guide.
- Coded by a former non-technical turned full stack dev so non-technicals don't waste their time doing this.
- Instructions tailored for macOS (I am too stupid/lazy to tailor for Windows/Linux).
- These scripts are tailored for Obsidian, but also work if you just want to create tagged, summarized `.md` files of all your ChatGPT chats.
- This script uses the OpenAI API, which costs money. It should be less than a dollar in cost; my chats were obscenely large and even they only cost around $3 total, with testing included. General cost is around 15 cents per 1 million tokens or around 20 cents per 1 million words.

---

## Install Instructions

1. Download the `sort_GPT` folder with all its contents.

---

## Usage

1. Export data from ChatGPT (Settings → Data Controls → Export Data)
2. Download data from the email you receive.
3. Keep the data in zip file form and move it into the `sort_GPT` folder.
4. Log into OpenAI at [https://platform.openai.com]
5. Add money to your account if there isn't any. It should be under $5.  
   Billing link: [https://platform.openai.com/settings/organization/billing/overview]
6. View your API keys here: [https://platform.openai.com/api-keys]
7. Create a new secret key with a name of your choice and permissions "All."  
   (You can also just copy an existing key if you already have one.)
8. Copy the new (or existing) secret key.
9. Open Mac Terminal.
10. In Terminal, run:

    ```bash
    export OPENAI_API_KEY="YOUR_SECRET_KEY_GOES_HERE"
    ```

11. In Terminal, navigate to the `sort_GPT` folder using the `cd` command.
12. Run:

    ```bash
    python3 sort.py
    ```

    - This step will take a while the very first time. It runs in the background at a rate of around 150 words per second.  
      It took me more than ten hours on my first run; after that it was down to about 20 minutes for every time after.
    - It shouldn’t slow your computer down too much unless it’s already taxed; you can broadly use it for other purposes while it happens.
    - To prevent your computer from sleeping, open a new terminal and run:
      ```bash
      caffeinate -dimsu
      ```
    - Also go to System Settings → Lock Screen and set:
      - “Turn display off on battery when inactive” → Never
      - “Turn display off on power adapter when inactive” → Never
    - When done, hit Ctrl + C on the terminal running `caffeinate -dimsu` and revert Lock Screen settings to normal.
    - If your Mac accidentally turns off/falls asleep and the process is terminated halfway, just open Terminal, navigate back to the `sort_GPT` folder with `cd`, and run:
      ```bash
      python3 sort.py
      ```
      again. Then open a new Terminal and run `caffeinate -dimsu` again.  
      The script will collate all files it didn’t manage to complete and start off where it stopped.

Repeat steps 1–12 of Usage whenever convenient to keep the database up to date.

---

### Obsidian Install

1. Download Obsidian [https://obsidian.md].
2. Open a folder as a vault in Obsidian. Use the `Final_MD` folder.
3. Download the Dataview plugin inside Obsidian.  
   (Settings → Community Plugins → Turn On Community Plugins → Browse → Dataview → Install → Enable)
4. Enable JavaScript Queries and Inline JavaScript Queries for Dataview.  
   (Settings → Dataview → Enable JavaScript Queries + Enable Inline JavaScript Queries)
5. Search up `dashboard.md` in the vault search bar and click it to observe the result.

---

## Dashboard Usage

- If the dashboard shows up as raw code, you're in edit mode. Click the book icon in the top-right corner to go into view mode.
- The dashboard has six filter fields. It will appear empty until you actually search for something.  
  If you want all the chats listed, just use a filter that will catch every file (for example, the date range from today to 100 years ago).
- The first two fields are Start Date and End Date. By entering values, you ensure that chats from only that time range show up in the table.  
  Note: The time range references the day the chat was created, not when it was last updated.
- Fields 3–6 are Title, Tag, Summary, and Content respectively.  
  They can all be searched by "quoted AND" search and/or "quoted NEG" search, and also by regular "contains" search.

### Search Examples

- Typing `food` into the content search bar finds any chats containing `food` within their content.
- Typing `"food" "eat"` performs "quoted AND" search, finding chats that contain *both* `food` and `eat`.
- Typing `-"hungry"` excludes chats containing the word `hungry`.
- Thus, `"food" "eat" -"hungry"` in the content filter returns all chats containing exactly `food` and `eat` but NOT `hungry`.

### Field Details

- Title field: Contains chat titles generated without commas or special characters. Keep this in mind when using "quoted AND" or "quoted NEG" search.
- Tag field: Uses a nested convention. For example, a tag of `misc` contains tags like:
  - `misc`
  - `misc/food`
  - `misc/books`
  - `misc/books/fantasy`  
  The dashboard is generated with 10–15 `misc/...` tags per chat.  
  I recommend pruning them as you go and adding tags that encompass big ideas in the conversation that are easy to remember.  
  You can also use nested tags to easily organize projects.
- Summary field: Contains a 100–150 word AI summary of the chat. These summaries are not always accurate; I recommend refining them as you go.

---

## Requirements

- macOS (tested)
- Python 3.10+
- OpenAI API key with billing enabled
- (Optional) Obsidian + Dataview plugin for dashboard functionality

---

## License

MIT License (feel free to reuse, modify, or redistribute)
