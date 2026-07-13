---
name: kis-api-reference
description: Use when the user asks anything about the 한국투자증권 / 한투 / KIS open-trading-api — auth/토큰, TR_ID, 국내·해외 주식 시세/주문/잔고, 실시간 WebSocket 체결·호가, 봉/기간 조회, 어떤 엔드포인트·헤더·파라미터를 써야 하는지. Look up the real example in koreainvestment/open-trading-api before answering.
---

# KIS (한국투자증권) API Reference

Answering KIS questions from memory is unreliable — TR_ID, header, and field
names change per market and per KRX/NXT/통합. **Always look up the real example
in `koreainvestment/open-trading-api` first, then answer.**

Repo: https://github.com/koreainvestment/open-trading-api (branch `main`)

## Where to look

`examples_llm/` is the source of truth. One API = a pair of files:
- `<name>.py` — the request function (URL, TR_ID, headers, params)
- `chk_<name>.py` — how to call it / expected response fields

Folders by asset class:

| Question is about | Folder |
|---|---|
| 토큰 발급, approval_key (websocket 접속키), hashkey | `examples_llm/auth/` |
| 국내주식 시세·주문·잔고·체결·호가 | `examples_llm/domestic_stock/` |
| 해외주식 | `examples_llm/overseas_stock/` |
| 국내 채권 | `examples_llm/domestic_bond/` |
| 국내 선물·옵션 | `examples_llm/domestic_futureoption/` |
| 해외 선물·옵션 | `examples_llm/overseas_futureoption/` |
| ELW / ETF·ETN | `examples_llm/elw/`, `examples_llm/etfetn/` |

Filename hints inside a folder: `asking_price*`=호가, `ccnl*`=체결,
`dailyprice`/`inquire_daily*`=일별시세, `_krx`/`_nxt`/`_total`=거래소 구분(통합=total),
`order*`=주문, `balance*`=잔고. Realtime WebSocket examples live in the same
asset folders (the ones subscribing to 실시간 체결/호가).

Other useful spots:
- `MCP/` KIS Code Assistant has `data.csv` — a full API index if a keyword search of the tree fails.
- `docs/convention.md` — naming conventions.

## How to find the exact file

Grep the repo tree for a keyword, then read the raw file:

```bash
# find candidate files
curl -s "https://api.github.com/repos/koreainvestment/open-trading-api/git/trees/main?recursive=1" \
  | python3 -c "import json,sys; [print(e['path']) for e in json.load(sys.stdin)['tree'] if 'KEYWORD' in e['path']]"

# read one (WebFetch the raw URL, or curl)
# https://raw.githubusercontent.com/koreainvestment/open-trading-api/main/examples_llm/<folder>/<name>.py
```

When reading an example, pull out exactly: **TR_ID**, request **URL path**,
required **headers** (`tr_id`, `custtype`, `tr_cont` 연속조회, etc.), **query/body
params** (map coded params to the Enum names this project uses), and the
**response field names**.

## How to answer (this project is learning mode)

Per this repo's CLAUDE.md, the user writes the implementation. So:
- **Do not write the function body / client logic.** Explain the concept, cite the exact example file + line, give the TR_ID / header / param mapping in prose or a table, and let the user code it.
- Prefer pointing at `app/kis/` structure this project already has (`korea/`, `overseas/`, `websocket/`, `schemas/`) and where the new call fits.
- Coded param sets (기간분류, 거래소구분 등) → suggest an `Enum`; grouped params → a Pydantic `BaseModel`, matching this project's rules.

## Common mistakes

- Answering TR_ID / field names from memory — verify against the example file.
- Confusing KRX vs NXT vs 통합(total) endpoints — check the filename suffix.
- Forgetting `tr_cont` for 연속조회(paging) or `approval_key` (not the REST token) for WebSocket.
- 모의투자 vs 실전 use different TR_ID prefixes and base URLs — confirm which the user is on.
