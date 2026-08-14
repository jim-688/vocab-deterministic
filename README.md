# vocab-deterministic — 零 token 背单词系统

> **已归档**：本项目是 [wordvault](https://github.com/jim-688/wordvault) 的前身/早期引擎版。wordvault 为正式版（含完整词库、LICENSE、examples），日常使用请前往 wordvault。

一个**大模型零参与**的背单词引擎：本地脚本判定对错、JSON 存进度、艾宾浩斯曲线调度复习。AI 只做每周留存率分析（可选），日常教学/测试/统计全部走确定性代码。

## 设计思路（为什么值得看）

核心原则：**能确定性解决的问题，不交给大模型。**

```
用户输入
  │
  ├─ 测试判分   → vocab_test.py（本地，零 token）
  ├─ 进度存储   → progress.json + 艾宾浩斯调度（本地）
  ├─ 发音       → edge-tts 本地缓存（零 LLM）
  ├─ 健康统计   → vocab_stats.py（本地）
  └─ 留存率分析 → AI 每周一次（唯一允许用 LLM 的地方）
```

对比传统"AI 背单词 App"：
- 每次测试都调大模型 → 每天几百上千 token，长期成本高
- 本方案 → 测试/调度/统计全部本地，AI 一周只工作一次，几百 token/周

## 调度策略（艾宾浩斯）

- 答错：1 → 2 → 4 → 7 → 15 天（间隔递增）
- 答对：7 → 15 → 30 天
- 三态判定：`correct` / `wrong` / `unknown`（unknown = 完全不会，比 wrong 更弱，复习间隔更短）
- 错因记录：`meaning` / `spelling` / `confusion` / `unknown`，积累后给 AI 做留存率分析

## 文件

| 文件 | 作用 |
|---|---|
| `vocab_test.py` | 主引擎：出题、判分、更新进度、调度复习 |
| `vocab_stats.py` | 健康统计：掌握率、反复出错词、复习逾期提醒 |

## 用法

```bash
# 查看进度
python vocab_test.py status

# Day1 中→英测试（输出题目）
python vocab_test.py test day1 cn

# Day1 英→中测试
python vocab_test.py test day1 en

# Day1 只测错词
python vocab_test.py review day1

# 提交答案（JSON），更新进度
python vocab_test.py check day1 '<answers_json>'
```

## 数据格式

`words.json`（词库，需自行准备）：

```json
[
  {"word": "abandon", "meaning": "放弃", "day": 1}
]
```

`progress.json`（学习状态，脚本自动生成）：

```json
{
  "day1": {
    "words": {
      "abandon": {
        "status": "wrong",
        "count": 2,
        "review_history": [
          {"result": "wrong", "reason": "confusion", "date": "2026-08-11"}
        ]
      }
    }
  }
}
```

## 说明

- 词库来源：个人教材提取，仅作学习用途，随仓库附带的 `words.json` 不含（请自行准备词表）。
- 发音依赖 `edge-tts`（微软免费 TTS），首次生成后缓存到 `audio/`，之后离线可用。

## License

MIT
