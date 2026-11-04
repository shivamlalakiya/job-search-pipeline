#!/bin/zsh
# Scout -> run_bulk loop until TARGET new submissions on the active profile.
# Widens the posting window (1, 3, 7, 14, 30 days) once a window's keywords
# stop yielding anything to apply to. WINDOWS="2" limits it to one window.
# Log: <profile>/campaign.log
cd "${0:A:h}"
TARGET=${1:-500}
KEYWORDS=("data analyst" "business analyst" "marketing analyst" "business intelligence analyst"
  "reporting analyst" "analytics analyst" "marketing data analyst" "data visualization analyst"
  "product analyst" "operations analyst" "insights analyst" "digital analytics analyst"
  "power bi developer" "tableau developer" "sql analyst" "growth analyst" "research analyst"
  "financial data analyst" "healthcare data analyst" "crm analyst")
PROFILE=profiles/$(cat PROFILE)
# A profile's own titles, one per line, replace the analytics defaults above.
[[ -s $PROFILE/keywords.txt ]] && KEYWORDS=("${(@f)$(<$PROFILE/keywords.txt)}")
LOG="$PROFILE/campaign.log"
submitted() { python3 -c "
import openpyxl;ws=openpyxl.load_workbook('$PROFILE/tracker.xlsx',read_only=True)['Applications']
print(sum(1 for r in ws.iter_rows(min_row=2,values_only=True) if r[7]=='submitted'))"; }
START=$(submitted)
echo "$(date) start: $START submitted, target +$TARGET" >> "$LOG"
for DAYS in ${=WINDOWS:-1 3 7 14 30}; do
  for KW in "${KEYWORDS[@]}"; do
    NOW=$(submitted)
    (( NOW - START >= TARGET )) && { echo "$(date) target reached: $NOW" >> "$LOG"; exit 0; }
    echo "$(date) scout '$KW' --days $DAYS (applied so far +$((NOW - START)))" >> "$LOG"
    python3 scout.py "$KW" --days $DAYS --pages 12 --track >> "$LOG" 2>&1
    python3 run_bulk.py >> "$LOG" 2>&1
  done
done
echo "$(date) keywords exhausted at 30 days: +$(( $(submitted) - START ))" >> "$LOG"
