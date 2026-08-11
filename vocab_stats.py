"""Vocab health stats for 吉冠佳 (zero-LLM, deterministic).
Reads progress.json review data, prints struggling words + activity summary.
"""
import json
import os
import sys
from datetime import date, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
PROGRESS_FILE = os.path.join(BASE, 'progress.json')


def main():
    if not os.path.exists(PROGRESS_FILE):
        print("[vocab_stats] progress.json not found")
        return
    p = json.load(open(PROGRESS_FILE, encoding='utf-8'))
    review = p.get('review', {})
    words = review.get('words', {})
    nw = p.get('new_words', {})

    if not words:
        print("[vocab_stats] no review words yet")
        return

    mastered = sum(1 for w in words.values() if w.get('mastered'))
    total = len(words)
    struggling = sorted(
        ((word, info.get('wrong', 0), info.get('tested', ''))
         for word, info in words.items() if (info.get('wrong', 0) or 0) >= 2),
        key=lambda x: -x[1],
    )[:10]

    # review activity: how many days since last test date overall
    dates = [datetime.strptime(w['tested'], '%Y-%m-%d').date()
             for w in words.values() if w.get('tested')]
    last_date = max(dates) if dates else None
    today = date.today()
    days_since = (today - last_date).days if last_date else None

    print("== 词汇健康（vocab_stats，零token）==")
    print(f"复习词总数: {total} | 已掌握: {mastered} ({mastered/total*100:.0f}%) | 未掌握: {total-mastered}")
    print(f"当前批次: 第 {nw.get('current_day','?')} 天 | 已学: {nw.get('total_learned','?')} | 下批起点: {nw.get('next_start_index','?')}")
    if last_date:
        print(f"最近一次测试: {last_date} ({days_since} 天前)" + (" ⚠️ 超过3天未复习" if days_since and days_since > 3 else ""))
    print()
    if struggling:
        print("反复出错词（wrong≥2，FSRS 调度会优先复习）:")
        for word, cnt, tested in struggling:
            print(f"  {word} ×{cnt}（{tested}）")
    else:
        print("无反复出错词 ✅")
    print()
    # Ebbinghaus ladder status
    due = 0
    for word, info in words.items():
        if info.get('mastered'):
            continue
        reviews = info.get('reviews', [])
        if not reviews:
            due += 1
            continue
        last = datetime.strptime(reviews[-1], '%Y-%m-%d').date()
        wrong_n = info.get('wrong', 0)
        intervals = [1, 2, 4, 7, 15]
        idx = len(reviews) - 1
        interval = 1 if wrong_n >= 2 else (intervals[idx] if idx < len(intervals) else 15)
        if (today - last).days >= interval:
            due += 1
    print(f"今日到期复习: {due} 词（可用 vocab_test.py due 查看）")


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f"[vocab_stats] FAILED: {exc}", flush=True)
        import traceback
        traceback.print_exc()
