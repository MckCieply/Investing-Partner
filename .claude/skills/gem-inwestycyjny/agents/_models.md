# Modele i Effort — konfiguracje

## Domyślna konfiguracja (Optymalna)

| Agent | Model | Effort | Plik |
|-------|-------|--------|------|
| 01 Scout | sonnet | HIGH | `agents/01-scout.md` |
| 02 Quant | haiku | NONE | `agents/02-quant.md` |
| 03 Alpha | sonnet | MEDIUM | `agents/03-alpha.md` |
| 04 Auditor | sonnet | HIGH | `agents/04-auditor.md` |
| 05 Director | sonnet | LOW | `agents/05-director.md` |

## Scenariusz Lean (oszczędność kosztu)

Gdy budżet jest priorytetem:

| Agent | Model | Effort |
|-------|-------|--------|
| 01 Scout | sonnet | HIGH |
| 02 Quant | haiku | NONE |
| 03 Alpha | sonnet | MEDIUM |
| 04 Auditor | sonnet | HIGH |
| 05 Director | haiku | LOW |

Oszczędność: ~15% vs Optymalny, kosztem nieco mniej eleganckiego stylu Directora.

## Scenariusz Maximum Quality

Gdy chcesz najlepsze możliwe decyzje (Opus dla decision-makerów):

| Agent | Model | Effort |
|-------|-------|--------|
| 01 Scout | opus | HIGH |
| 02 Quant | haiku | NONE |
| 03 Alpha | sonnet | HIGH |
| 04 Auditor | opus | HIGH |
| 05 Director | sonnet | MEDIUM |

Korzyść: Opus na Scoucie wyłapie trzecio-pochodne plays i niszowe motywy. Opus na Auditorze rzadziej "się zgadza" pod presją mocnej narracji.

Koszt: ~3x vs Optymalny.

## Dlaczego nie jednolicie Opus na wszystko

1. **Quant nie korzysta z reasoning** — czysty execution. Każdy dolar wydany tu = zmarnowany.
2. **Director ma tylko tłumaczyć decyzje** — Opus tutaj czasem dodaje "własne przemyślenia" mimo zakazu.
3. **Cały pipeline z Opusem to ~5x koszt** vs mix Sonnet+Haiku, bez 5x lepszego wyniku.

## Override per-run

Użytkownik może wymusić konfigurację argumentem do skilla:
- `/gem-inwestycyjny --quality=max` → Maximum Quality
- `/gem-inwestycyjny --quality=lean` → Lean
- Bez argumentu → Optymalna (domyślna)

## Najważniejsze: thinking effort

Najwięcej ROI zyskasz z:
- **Scout HIGH** — bez extended thinking model olewa filtry i wraca do mainstream picków
- **Auditor HIGH** — bez extended thinking model zbyt szybko daje "ZATWIERDZONO"

Te dwa nie obniżaj nawet w scenariuszu Lean.
