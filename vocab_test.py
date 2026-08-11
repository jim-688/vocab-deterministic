#!/usr/bin/env python3
"""
本地零token单词测试脚本 — 四级词汇闪过
用法:
  python vocab_test.py status         → 查看进度
  python vocab_test.py test day1 cn   → Day1 中→英测试，输出题目
  python vocab_test.py test day1 en   → Day1 英→中测试，输出题目
  python vocab_test.py review day1    → Day1 只测错词
  python vocab_test.py check day1 <answers_json>  → 输入答案，更新进度
"""
import json, os, sys, re, random
from datetime import date

BASE = os.path.dirname(os.path.abspath(__file__))
WORDS_FILE = os.path.join(BASE, 'words.json')
PROGRESS_FILE = os.path.join(BASE, 'progress.json')

def load_words():
    with open(WORDS_FILE, 'r', encoding='utf-8') as f:
        all_words = json.load(f)
    # Filter out non-word entries (headers, separators)
    words = []
    for w in all_words:
        word = w['word'].strip()
        meaning = w['meaning'].strip()
        if word.startswith('═') or word.startswith('共') or word.startswith('Day'):
            continue
        if not word or not meaning:
            continue
        if len(word) > 30:
            continue
        words.append(w)
    return words

def get_audio(word):
    """TTS audio for a word, cached in audio/ (edge-tts, zero LLM).
    Returns absolute path or None on failure."""
    audio_dir = os.path.join(BASE, 'audio')
    os.makedirs(audio_dir, exist_ok=True)
    path = os.path.join(audio_dir, f"{word}.mp3")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        return path
    try:
        import asyncio, edge_tts
        async def _gen():
            tts = edge_tts.Communicate(word, voice='en-US-JennyNeural')
            await tts.save(path)
        asyncio.run(_gen())
        return path if os.path.exists(path) else None
    except Exception:
        return None


def load_progress():
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def load_teaching_data():
    tf = os.path.join(BASE, 'teaching_data.json')
    if os.path.exists(tf):
        with open(tf, 'r', encoding='utf-8') as f:
            return {w['word']: w for w in json.load(f)}
    return {}

def save_progress(progress):
    with open(PROGRESS_FILE, 'w', encoding='utf-8') as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)

def get_day_words(all_words, day_config):
    """Get word list for a given day from progress config"""
    start = day_config.get('start_index', 0)
    count = day_config.get('word_count', 30)
    return all_words[start:start + count]

def cmd_status():
    progress = load_progress()
    if not progress:
        print(json.dumps({"status": "no_progress"}, ensure_ascii=False))
        return
    
    result = {"days": {}}
    for day, data in progress.items():
        stats = data.get('stats', {})
        words_data = data.get('words', {})
        wrong_words = [w for w, info in words_data.items() if info.get('status') == 'wrong']
        very_bad = [w for w in wrong_words if words_data[w].get('count', 0) >= 2]
        
        result['days'][day] = {
            'total': data.get('word_count', 0),
            'mastered': stats.get('mastered', 0),
            'struggling': stats.get('struggling', 0),
            'wrong_count': len(wrong_words),
            'very_bad_count': len(very_bad),
            'very_bad': very_bad
        }
    
    print(json.dumps(result, ensure_ascii=False))

def cmd_test(day_name, direction):
    """Generate test questions"""
    all_words = load_words()
    progress = load_progress()
    
    if day_name not in progress:
        print(json.dumps({"error": f"Day '{day_name}' not found in progress"}, ensure_ascii=False))
        return
    
    day = progress[day_name]
    words_data = day.get('words', {})
    word_list = get_day_words(all_words, day)
    
    questions = []
    for w in word_list:
        word = w['word'].lower()
        # Skip if word not in progress (shouldn't happen)
        if word not in words_data:
            continue
        
        if direction == 'en':
            # 英→中: show English, ask for Chinese
            questions.append({
                'id': len(questions),
                'type': 'en_zh',
                'prompt': word,
                'expected': w['meaning']
            })
        elif direction == 'audio':
            # 听音选义: play TTS audio, pick correct Chinese meaning from 4 options
            # (listening is 35% of CET-4; zero-LLM via edge-tts local cache)
            audio_path = get_audio(word)
            if audio_path is None:
                continue
            correct = w['meaning'].split(';')[0].split('vt.')[0].strip()
            if len(correct) > 30:
                correct = correct[:27] + '...'
            distractor_pool = [x['meaning'].split(';')[0].split('vt.')[0].strip()
                               for x in word_list if x['word'].lower() != word]
            distractor_pool = [d[:30] for d in distractor_pool if d]
            distractors = []
            for d in distractor_pool:
                if d != correct and d not in distractors:
                    distractors.append(d)
                if len(distractors) >= 3:
                    break
            options = distractors[:3] + [correct]
            random.shuffle(options)
            questions.append({
                'id': len(questions),
                'type': 'audio',
                'prompt': audio_path,  # MEDIA file Hermes plays inline
                'options': options,
                'expected': correct,
                'expected_id': options.index(correct)
            })
        else:
            # 中→英: show meaning (first 40 chars), ask for English
            meaning_short = w['meaning'].split(';')[0].split('vt.')[0].strip()
            if len(meaning_short) > 40:
                meaning_short = meaning_short[:37] + '...'
            questions.append({
                'id': len(questions),
                'type': 'zh_en',
                'prompt': meaning_short,
                'expected': word
            })
    
    print(json.dumps(questions, ensure_ascii=False))

def cmd_review(day_name):
    """Only test wrong words"""
    all_words = load_words()
    progress = load_progress()
    
    if day_name not in progress:
        print(json.dumps({"error": f"Day '{day_name}' not found"}, ensure_ascii=False))
        return
    
    day = progress[day_name]
    words_data = day.get('words', {})
    word_list = get_day_words(all_words, day)
    
    # Find wrong words, sorted by error count (most errors first)
    wrong = []
    for w in word_list:
        word = w['word'].lower()
        if word in words_data and words_data[word].get('status') == 'wrong':
            wrong.append({**w, 'count': words_data[word].get('count', 1)})
    
    wrong.sort(key=lambda x: -x['count'])
    
    questions = []
    for i, w in enumerate(wrong):
        meaning_short = w['meaning'].split(';')[0].split('vt.')[0].strip()
        if len(meaning_short) > 40:
            meaning_short = meaning_short[:37] + '...'
        questions.append({
            'id': i,
            'type': 'zh_en',
            'prompt': meaning_short,
            'expected': w['word'].lower(),
            'error_count': w['count']
        })
    
    result = {
        'day': day_name,
        'total_wrong': len(wrong),
        'questions': questions
    }
    print(json.dumps(result, ensure_ascii=False))

def cmd_teach(day_name):
    """Output teaching content for a day's words from local JSON"""
    progress = load_progress()
    teaching = load_teaching_data()
    
    if day_name not in progress:
        print(json.dumps({"error": f"Day '{day_name}' not found"}, ensure_ascii=False))
        return
    
    day = progress[day_name]
    words_data = day.get('words', {})
    word_list = [w for w in words_data.keys() if words_data[w].get('status') in ('new', 'wrong')]
    
    if not word_list:
        print(json.dumps({"message": "All words mastered! Nothing to teach."}, ensure_ascii=False))
        return
    
    result = []
    for word in word_list:
        td = teaching.get(word, {})
        if td:
            result.append({
                'word': word,
                'meaning': td.get('meaning', ''),
                'root': td.get('root', ''),
                'synonyms': td.get('synonyms', []),
                'lookalike': td.get('lookalike', []),
                'example': td.get('example', '')
            })
        else:
            # Fallback: just show word + meaning from words.json
            result.append({'word': word, 'meaning': words_data[word].get('meaning', ''), 'fallback': True})
    
    output = {
        'day': day_name,
        'total': len(result),
        'words': result
    }
    print(json.dumps(output, ensure_ascii=False))

def cmd_due():
    """Show words due for review today (Ebbinghaus curve)"""
    progress = load_progress()
    if 'review' not in progress:
        print(json.dumps({"error": "No review data found"}, ensure_ascii=False))
        return
    
    review = progress['review']
    today_str = date.today().isoformat()
    
    due_words = []
    for word, info in review.get('words', {}).items():
        if info.get('mastered'):
            continue
        last_tested = info.get('tested', '')
        if last_tested:
            last_date = date.fromisoformat(last_tested)
        else:
            last_date = date.today()
        days_since = (date.today() - last_date).days
        intervals = review.get('intervals', [1, 2, 4, 7, 15])
        reviews_done = info.get('reviews', [])
        next_idx = len(reviews_done) - 1
        # FSRS-inspired adaptive interval (2026-08-10, learned from open-spaced-repetition/fsrs4anki):
        # high-error words are harder -> shorter interval (review tomorrow);
        # clean words follow the Ebbinghaus ladder.
        wrong_n = info.get('wrong', 0)
        if wrong_n >= 2:
            interval = 1
        elif next_idx >= 0 and next_idx < len(intervals):
            interval = intervals[next_idx]
        else:
            interval = 1
        if days_since >= interval:
            due_words.append(word)
    
    output = {
        "date": today_str,
        "due_count": len(due_words),
        "total_review": len([w for w in review.get('words', {}) if not review['words'][w].get('mastered')]),
        "mastered": len(review.get('mastered', [])),
        "due_words": due_words
    }
    print(json.dumps(output, ensure_ascii=False))

def normalize(s):
    """Normalize answer for comparison"""
    s = s.strip().lower()
    # Remove punctuation
    s = re.sub(r'[^\w\s]', '', s)
    # Remove articles
    s = re.sub(r'\b(a|an|the|to)\b', '', s).strip()
    return s

def cmd_check(day_name, answers_json):
    """Process answers and update progress (v1.1: three-state + wrong_reason)
    Each answer supports:
      result:  "correct" | "wrong" | "unknown"   (unknown = 完全不会，比wrong更弱)
      reason:  "meaning" | "spelling" | "confusion" | "unknown"
    Records go to word['review_history'] for later analysis.
    """
    answers = json.loads(answers_json)
    all_words = load_words()
    progress = load_progress()
    
    if day_name not in progress:
        print(json.dumps({"error": "Day not found"}, ensure_ascii=False))
        return
    
    day = progress[day_name]
    words_data = day.get('words', {})
    word_list = get_day_words(all_words, day)
    
    # Build word lookup
    word_map = {w['word'].lower(): w for w in word_list}
    
    correct_count = 0
    wrong_count = 0
    unknown_count = 0
    results = []
    
    for ans in answers:
        word = ans.get('word', '').lower()
        user_answer = ans.get('answer', '').strip()
        was_wrong = ans.get('wrong', False)
        result = ans.get('result', 'wrong' if was_wrong else 'correct')
        reason = ans.get('reason', 'unknown')
        
        if word not in words_data:
            continue
        
        info = words_data[word]
        if 'review_history' not in info:
            info['review_history'] = []
        
        if result == 'unknown' or (was_wrong and result == 'wrong' and not user_answer and '不知道' in str(ans.get('answer', ''))):
            # 完全不会：仍算错（要复习），但标记为 unknown 供分析
            result = 'unknown'
            info['status'] = 'wrong'
            info['count'] = info.get('count', 0) + 1
            unknown_count += 1
            results.append({'word': word, 'status': 'wrong', 'result': 'unknown'})
        elif result == 'wrong' or was_wrong:
            info['status'] = 'wrong'
            info['count'] = info.get('count', 0) + 1
            wrong_count += 1
            results.append({'word': word, 'status': 'wrong', 'result': 'wrong',
                            'your_answer': user_answer, 'correct': ans.get('expected', word.lower())})
        else:
            # Compare: multiple-choice (audio/en_zh) uses expected_id, else exact match
            if 'expected_id' in ans and isinstance(ans.get('expected_id'), int):
                if user_answer.isdigit():
                    ok = int(user_answer) == ans['expected_id']
                else:
                    ok = normalize(user_answer) == normalize(ans.get('expected', ''))
            else:
                ok = normalize(user_answer) == normalize(word.lower())
            if ok:
                info['status'] = 'correct'
                info['count'] = info.get('count', 0) + 1
                correct_count += 1
                results.append({'word': word, 'status': 'correct', 'result': 'correct'})
            else:
                info['status'] = 'wrong'
                info['count'] = info.get('count', 0) + 1
                wrong_count += 1
                results.append({'word': word, 'status': 'wrong', 'result': 'wrong',
                                'your_answer': user_answer, 'correct': ans.get('expected', word.lower())})
        
        # 错因日志（只记答错/不会的）
        if result != 'correct':
            if 'wrong_reason' not in info:
                info['wrong_reason'] = []
            if reason not in info['wrong_reason']:
                info['wrong_reason'].append(reason)
        
        # 追加复习历史
        info['review_history'].append({
            'result': result,
            'reason': reason,
            'date': str(date.today())
        })
        
        info['last_tested'] = str(date.today())
    
    # Update stats
    mastered = sum(1 for w in words_data.values() if w.get('status') == 'correct' and w.get('count', 0) >= 2)
    struggling = sum(1 for w in words_data.values() if w.get('status') == 'wrong')
    
    day['stats'] = {
        'mastered': mastered,
        'struggling': struggling,
        'new': day.get('word_count', 30) - mastered - struggling
    }
    
    save_progress(progress)
    
    result = {
        'day': day_name,
        'total': len(answers),
        'correct': correct_count,
        'wrong': wrong_count,
        'unknown': unknown_count,
        'results': results,
        'stats': day['stats']
    }
    print(json.dumps(result, ensure_ascii=False))

def cmd_wrong_analysis():
    """Analyze wrong_reason distribution + top problem words (v1.1)"""
    progress = load_progress()
    review = progress.get('review', {})
    words = review.get('words', {})
    
    # 只分析有错因记录的词（v1.1之后才有）
    reason_counts = {}
    hard_words = []
    recent_unknown = []
    
    for w, info in words.items():
        reasons = info.get('wrong_reason', [])
        for r in reasons:
            reason_counts[r] = reason_counts.get(r, 0) + 1
        wrong_n = info.get('wrong', 0)
        if wrong_n >= 2:
            hard_words.append({'word': w, 'wrong': wrong_n, 'reasons': reasons})
        # 最近一次是 unknown 的词
        hist = info.get('review_history', [])
        if hist and hist[-1].get('result') == 'unknown':
            recent_unknown.append(w)
    
    hard_words.sort(key=lambda x: -x['wrong'])
    
    output = {
        'reason_distribution': reason_counts,
        'hard_words_count': len(hard_words),
        'hard_words': hard_words[:20],
        'recent_unknown_count': len(recent_unknown),
        'recent_unknown': recent_unknown[:30],
        'total_words': len(words)
    }
    print(json.dumps(output, ensure_ascii=False))

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("用法: python vocab_test.py [status|test|review|check|teach|due|wrong-analysis] [args...]")
        sys.exit(1)
    
    cmd = sys.argv[1]
    
    if cmd == 'status':
        cmd_status()
    elif cmd == 'test' and len(sys.argv) >= 4:
        cmd_test(sys.argv[2], sys.argv[3])
    elif cmd == 'review' and len(sys.argv) >= 3:
        cmd_review(sys.argv[2])
    elif cmd == 'check' and len(sys.argv) >= 4:
        cmd_check(sys.argv[2], sys.argv[3])
    elif cmd == 'teach' and len(sys.argv) >= 3:
        cmd_teach(sys.argv[2])
    elif cmd == 'due':
        cmd_due()
    elif cmd == 'wrong-analysis':
        cmd_wrong_analysis()
    else:
        print(f"Unknown command or missing args: {cmd}")
        sys.exit(1)
