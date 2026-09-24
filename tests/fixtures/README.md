# Dane demo (fikcyjne)

Te pliki **nie są** prawdziwym portfelem — to fikcyjne pozycje i rekomendacje na
płynnych, publicznie znanych spółkach (ceny wejścia wymyślone). Prawdziwe dane żyją
w prywatnym repo `investing-partner-data` i nigdy nie trafiają do tego repo ani do
jego logów CI.

Używa ich workflow [`ci.yml`](../../.github/workflows/ci.yml), który na każdy push
odpala cały deterministyczny tor (auditor → auto-log zamknięcia → re-entry scanner →
re-entry context → performance digest) z pełnym outputem w logu, żeby było widać,
jak system działa — bez ujawniania czegokolwiek prawdziwego.
