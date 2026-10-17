# Требования и трассировка реализации

Исходники: «Medkit (1).pdf» и «MEDKIT PRD_SRS_UserStories_RTM.pdf». Детальный SRS принят за источник точных правил; краткая концепция использована для определения пользовательского сценария. Требование в PDF «отдельный PR» не трактовалось как поручение публиковать код: работа выполнена локально.

**Обозначения:** «реализовано» означает наличие кода; «проверено» — наличие выполненного теста. Ни один из этих статусов сам по себе не означает полную приёмку P0. Ссылки на тесты — фактические имена в репозитории, исходные TC сохранены для сопоставления.

## Функциональные требования

| Требование SRS | Реализация | Проверка / оставшаяся работа |
|---|---|---|
| FR-AUTH-001, TC-001/036 | Argon2id, серверная сессия, одинаковый LOGIN_FAILED, лимит попыток | test_auth_and_csrf, test_rate_limit |
| FR-AUTH-002, TC-002/030 | Роль, организация, владелец черновика | test_roles_and_isolation, test_cancel_ownership_reason_and_reopen |
| FR-AUTH-003, TC-021 | Выход, отзыв хеша сессии, удаление cookie | test_logout_revokes_session, test_logout_expired_session_is_safe |
| FR-ORG-001, TC-017 | Проверка org_id, чужие объекты → 404 | test_roles_and_isolation; расширить комбинации всех write/OCR-методов |
| FR-KIT-001, TC-003/030 | Создание, изменение, архив; запрет архива при DRAFT | test_snapshot_survives_renaming_new_template_archive_and_pdf, test_cancel_ownership_reason_and_reopen |
| FR-KIT-002, TC-003 | Случайный постоянный public_code, QR PNG с URL | Код реализован; физическое сканирование телефоном не проверено |
| FR-KIT-003, TC-003/017 | URL /q/:code, вход перед доступом, архивная история | Чужой код проверен; browser smoke вход/карточка пройден |
| FR-TPL-001, TC-022/004 | Шаблоны и неизменяемые версии | Проверена смена версии и сохранность снимка |
| FR-TPL-002, TC-022 | Норма 0–9999, единица, флаг контроля, 1–50 строк | Pydantic; исчерпывающий тест всех границ названий остаётся |
| FR-TPL-003, TC-023/004 | Привязка аптечки к шаблону той же организации | Чужой template_id отклоняется; API и UI реализованы |
| FR-TPL-004, TC-004/015/033 | Снимок шаблона и реквизитов; CONFIG_CHANGED | test_snapshot_survives_renaming_new_template_archive_and_pdf |
| FR-INSP-001, TC-030 | Единственный DRAFT, возобновление владельцем | test_revision_and_single_draft; конкурентный PostgreSQL stress ещё не проведён |
| FR-INSP-002, TC-004/015 | Снимок на старте | test_snapshot_survives_renaming_new_template_archive_and_pdf |
| FR-INSP-003, TC-005/006/025 | Обязательный подсчёт и подтверждение, пустое ≠ 0 | test_invalid_quantity_and_unconfirmed_month, test_blank_not_zero |
| FR-INSP-004, TC-024/025/027 | Группы дат и UNKNOWN; дата не нужна при нуле | test_ds_rules_1, test_invalid_facts, browser smoke |
| FR-INSP-005, TC-005/006/044 | SHORTAGE=max(R-A,0) | Все 12 строк DS-RULES-1 |
| FR-INSP-006, TC-007/008/024/026 | Просрочка только при date < inspection_date | test_ds_rules_1, test_date_based_on_completion_timezone |
| FR-INSP-007, TC-011/025/027 | Блокировка незаполненного чек-листа, сумм и подтверждений | test_incomplete_cannot_complete, test_invalid_facts |
| FR-INSP-008, TC-012/013/018/052 | Одна транзакция на завершение и расчёты | test_failed_commit_rolls_back_completion, test_trace_100_survives_engine_restart |
| FR-INSP-009, TC-026/027/044 | 1–20 групп, qty>0, сумма=A, обязательная причина UNKNOWN | test_ds_rules_1, test_invalid_facts |
| FR-INSP-010, TC-029/047 | Сохранение revision, 409 без перезаписи, индикация несохранённых правок | test_revision_and_single_draft, browser smoke; разрыв сети вручную не проведён |
| FR-INSP-011, TC-014/031 | Повтор complete возвращает исходный результат; запись закрыта | test_completion_idempotent_and_immutable |
| FR-INSP-012, TC-030 | Отмена владельцем/админом с причиной, новый старт | test_cancel_ownership_reason_and_reopen |
| FR-OCR-001, TC-010/034/047 | Фото/файл JPEG/PNG, ручной резервный ввод | test_upload_rejection, test_invalid_nested_item_and_upload; мобильная камера не проверена |
| FR-OCR-002, TC-009/010/024/043 | Tesseract, CANDIDATE/AMBIGUOUS/NOT_READ, EXP/MFG | test_ocr_parser; OCR-01 на реальных фото не проведён |
| FR-OCR-003, TC-009/024 | OCR не меняет строку; подтверждение, source, время и пользователь | Валидация validate_item и тест неподтверждённых дат |
| FR-DATE-001, TC-024/038 | Три формата, DAY/MONTH, MONTH_END_V1 | test_dates, test_invalid_dates, test_month_requires_separate_confirmation |
| FR-REP-001, TC-012/013/027/038 | Все причины и result, корректная подпись OK | DS-RULES-1, completion tests |
| FR-REP-002, TC-032 | История COMPLETED/CANCELLED, по 20, DESC time/id | TRACE-100, cancellation tests, UI истории |
| FR-REP-003, TC-015/017/042 | PDF только COMPLETED своей организации, архив доступен | Snapshot/PDF и access tests; максимальная нагрузка не измерена |
| FR-REP-004, TC-015/052 | ReportLab из снимка: реквизиты, версия, даты, группы и расчёты | PDF сформирован и визуально проверен; проверяется семантическая стабильность, не побайтовое равенство PDF |
| FR-REP-005, TC-016/033 | last_result, freshness, EXPIRED_SINCE, CONFIG_CHANGED | test_freshness_independent_from_historical_result, test_due_date_boundary |
| FR-REP-006, TC-028/044 | Раздельные суммы и replenish без двойного счёта | Все 12 DS-RULES-1 |
| FR-KIT-004 (P1) | Поиск + фильтр результата/обхода/архива в UI | Реализовано сверх базового ручного потока; автоматический UI-тест фильтров не добавлен |
| FR-AUD-001 (P1) | Расширенный неизменяемый журнал действий | Отложено |
| FR-OCR-004 (P1) | Технические OCR-метаданные и TTL | Отложено; фото и raw_text не сохраняются |

## Нефункциональные требования: зазоры до приёмки

| Область | Что есть | Что остаётся |
|---|---|---|
| PERF-001/002/003 | Локальные вычисления, отдельный поток OCR, лимиты очереди, PDF | Измерить p95 на PERF-01; общий deadline OCR с очередью/декодированием пока не равен требуемым 15 с |
| SEC-001 | Argon2id m=19456 KiB,t=2,p=1; пароль 12–128; лимит 10/15 мин | Лимит в памяти одного процесса, сбрасывается при перезапуске |
| SEC-002 | Серверные роли, владельцы и org_id | Внешнее security-review и полное покрытие всех вложенных ID |
| SEC-003 | HTTPS-профиль Caddy, Secure cookie через env | Реальный домен/TLS не разворачивались; локальный HTTP разрешён только для разработки |
| SEC-004 | 256-bit секрет, только хеш в БД, HttpOnly/Lax, CSRF/Origin, 30 мин/8 ч | Сквозная проверка через HTTPS-прокси остаётся |
| UPL-001 | Сигнатура + декодирование, 5 MiB/12 MP; очередь и лимиты | Multipart читает тело до endpoint; прокси ограничивает общий размер 6 MB |
| PRIV-001 | Нет изображений/raw_text в БД/отчётах; закрытие UploadFile | После аварии ОС spool требует tmpfs/очистки; формальный TTL 15 минут не реализован отдельной задачей |
| USAB-001/002 | Адаптивный CSS, подписи/текст ошибок, keyboard controls, dirty-state | Проверить 360 px и клавиатурой полный сценарий; моделировать сеть/ошибки камеры |
| REL-001 | Транзакции, CAS revision, повтор complete, SQLite TRACE-100 | Физический рестарт PostgreSQL и конкурентные сбои — отдельный стендовый протокол |
| REL-002 | backup/restore-скрипты, ротация 7 копий, инструкция | Расписание оператор устанавливает отдельно; измерить RPO/RTO на целевом стенде |
| COMP-001 | Выполнен локальный IAB smoke | Не пройдена матрица Chrome/Firefox/Edge/Android |
| TEST-001 | Эталон JSON и модульные/API/TRACE тесты | Расширить PostgreSQL concurrency/recovery |
| CI-001 | Workflow lint/types/tests/frontend/Docker | Фактический GitHub CI, branch protection, публикация образа и внешний review не выполнялись |
| OBS-001 | live/ready, JSON request_id/code/duration | ready проверяет наличие схемы v1; контроль последовательности будущих миграций нужен отдельно |
| OPS-001 | Docker, CLI орг/аккаунтов, скрытый пароль, reset/disable | Для эволюции схемы добавить Alembic |

## Почему нельзя объявить «все P0 пройдены»

В документе готовность зависит не только от наличия функций, но и от измеренных метрик USER-01, OCR-01, PERF-01, восстановления и браузерной матрицы. Для них нужны участники, фотографии, конкретный стенд и протокол. Реализация подготовлена к демонстрации; оставшиеся проверки перечислены явно, а результаты не подменены предположениями.
