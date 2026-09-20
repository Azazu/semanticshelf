# SemanticShelf — brief

Extracted from `Pet_Projects_Portfolio_Sopilko.md` (project 3). Original language: Russian.

## Проект 3 — SemanticShelf (Python/FastAPI + pgvector + CLIP)

Сервис семантического поиска по изображениям/ассетам. Это **прямая эволюция вашего ресёрча embedding-поиска** — самый сильный дифференциатор в портфолио и мост в AI-инженерию.

### Что показывает работодателю
Python-бэкенд (**FastAPI**, async, Pydantic), работа с **ML-моделями** и эмбеддингами (**CLIP** для text→image, **DINOv2** для image→image, при желании **CSD** для стиля), **векторная БД** (**PostgreSQL + pgvector**), проектирование поиска и API, Docker, pytest. Тот факт, что вы уже делали ресёрч и пайплайн по этой теме, делает проект достоверным.

### Функциональные требования
- Загрузка изображений (или подключение папки) → извлечение эмбеддингов → сохранение в pgvector.
- **Семантический поиск text→image**: запрос текстом («красный дракон в тумане») → похожие изображения (CLIP).
- **Поиск похожих image→image**: загрузить картинку → найти визуально близкие (DINOv2).
- (Опц.) **поиск по стилевому сходству** (CSD-ViT-L).
- Фильтры (теги/категории), пагинация, порог похожести.
- REST API (FastAPI) + простой UI (Streamlit или лёгкий React) для демо.
- (Стретч) RAG-описания: автогенерация подписи/тегов к изображению.

### Модель данных (PostgreSQL + pgvector)
- `assets` — `id`, `path/url`, `meta` (JSONB), `tags`.
- `embeddings` — `asset_id`, `model` (clip/dinov2/csd), `vector` (тип `vector`), индекс (HNSW/IVFFlat).

### Технологический стек
Python 3.12, FastAPI, Pydantic, SQLAlchemy + Alembic, PostgreSQL 16 + pgvector, open-source модели (CLIP-ViT-L/14, DINOv2-large), Docker, pytest. Тяжёлые вычисления эмбеддингов — фоново (background tasks или Celery).

### Чему учит / что демонстрирует
Python-бэкенд промышленного вида, интеграция ML-моделей, векторный поиск и индексы (HNSW/IVFFlat), async-API, проектирование под ресурсоёмкие задачи — плюс демонстрирует ваш AI-угол вживую, а не на словах.

### Этапы
1. FastAPI + Postgres/pgvector + загрузка изображений, генерация и хранение CLIP-эмбеддингов.
2. Поиск text→image + API + простой UI для демо.
3. image→image (DINOv2), фильтры, порог, пагинация, индексы.
4. Тесты, Docker, README с примерами; (стретч) стиль-поиск/RAG-описания.

---

