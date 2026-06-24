# Gem Inwestycyjny — Position Auditor (Agent 6)

Cotygodniowy audyt stopów dla otwartych pozycji (XTB IKE). Liczy poziomy
Sell Stop / plany transz per aktywo, pokazuje zmiany od ostatniego runu.
Przeznaczony do uruchamiania przez **Claude Code Routine** (niedziela rano).

## Uruchomienie lokalne
```bash
pip install -r requirements.txt
python skills/gem-position-auditor/position_auditor.py holdings.json
```
Stan zapisuje się do `stops_state.json` (MUSI być commitowany, inaczej znika diff tygodniowy).

## Aktualizacja pozycji
Edytuj `holdings.json` gdy zmienisz book. Pola: `xtb`, `yahoo`, `avg_cost`, opcjonalnie `is_etf`, `bucket`.

## Reguły i pełna logika
Patrz `skills/gem-position-auditor/SKILL.md` (Agent 6).
