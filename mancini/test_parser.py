"""Quick validation of parser against real Mancini email structure."""
import sys
sys.path.insert(0, '/root/projects/Strader')

from mancini.parser import parse_email, parse_levels

# Simulated excerpt matching the May 15 email structure
sample = """View this post on the web at https://example.com

Today, ES took its second breather in a week.
As I frequently discuss all major rallies in ES start on Failed Breakdowns.
**********Important Housekeeping Notices********
(NEW) Contract Roll: blah blah
FOR NEW READERS: essential to read methodology
The Run Down on The Level To Level Approach: What, Why, How
This section is intended for newer readers...
                                                  On to today: Basic Themes
Heading into today, I verified my positioning at the close yesterday at 4pm.
There were a few things to note heading into today:
1) Readers know about elevator down sell and short squeeze siblings.
We got this dynamic Wednesday morning.
2) The basic theme was ES had been rangebound with resistance at 7450-55.
3) Finally, don't use any of the above to make predictions.
With this in mind, let's look at how yesterday's execution plan applied.
                                                  Trade Recap/Daily Summary
NOTE: The purpose of this trade recap section is to run down examples.
                                                          Thursday Evening
Yesterday, we closed up at the high of day. There was nothing for me to do.
The first mini-Failed Breakdown was of 7507. At 1:20PM we set a 19 point low.
By 10pm, ES sold off to that 7496 support. By 1045pm, ES returned to 7507.
                             Friday Morning And The "Elevator Down" Sell To 7421
When I woke up at 730AM, ES was down at 7450-55. At 4:30AM, ES knifed through
to 7435. The reclaim of 7450-55 was actionable around 6:45AM. We popped to 7473.
                                              The 9:55AM 7435 Failed Breakdown
At 9:50AM we tagged 7421 exact and spiked out. From 430am to 930AM ES set a
shelf of lows at 7435. By selling to 7421 at 950AM, we lost that shelf. Shortly
after at 955am to 10am ES recovered the 7435 shelf and we ripped to 7460+.
Screenshot taken at 10:23AM Friday
Trade Plan Monday
Supports are: 7442, 7435 (major), 7427, 7421 (major), 7414, 7410, 7398 (major), 7390, 7383, 7377 (major).
In terms of lvls I'd bid direct: commentary here about levels.
Resistances are: 7449, 7458 (major), 7469, 7472 (major), 7482, 7489, 7496 (major).
As readers know I don't short ES.
Bull case Monday: ES finds itself in a range 7472 resistance and 7421 support.
Bear case Monday: Begins below 7421.
In summary for Monday: range mostly 7472 to 7421.
As always no crystal balls, no guessing, no predicting.

Unsubscribe https://example.com/unsub"""

result = parse_email(sample, date="2026-05-15", subject="Test")

print(f"Date: {result.date}")
print(f"Subject: {result.subject}")
print(f"\n--- REVIEW STEPS ({len(result.review_steps)}) ---")
for i, step in enumerate(result.review_steps):
    print(f"\n  Step {i+1}: {step.title}")
    print(f"  Time anchor: {step.time_anchor}")
    print(f"  Direction: {step.direction}")
    print(f"  Prices: {step.price_levels}")
    print(f"  Excerpt: {step.text_excerpt[:100]}...")

print(f"\n--- SUPPORTS ({len(result.support_levels)}) ---")
for lvl in result.support_levels:
    print(f"  {lvl.price} {lvl.annotation}")

print(f"\n--- RESISTANCES ({len(result.resistance_levels)}) ---")
for lvl in result.resistance_levels:
    print(f"  {lvl.price} {lvl.annotation}")

print(f"\n--- BASIC THEMES ---")
print(f"  Length: {len(result.basic_themes)} chars")
print(f"  Preview: {result.basic_themes[:120]}...")
