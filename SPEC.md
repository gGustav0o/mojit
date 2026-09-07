# Техническое задание: `mojit`

> **Статус документа:** реализованный контракт v1.0. Этот документ фиксирует
> существующее поведение text/effect режима и остаётся нормативным для обратной
> совместимости, пока активный roadmap явно не меняет конкретный контракт. Текущее
> направление развития продукта описано в [docs/PRODUCT.md](docs/PRODUCT.md),
> последовательность новой работы — в [docs/ROADMAP.md](docs/ROADMAP.md). Завершённые
> Phase 0-6 являются базой, а не конечной границей продукта.


## 1. Назначение

`mojit` — CLI-утилита для полноэкранного отображения Unicode-текста, прежде всего японского, в виде крупной анимированной графической композиции внутри терминала.

```powershell
mojit "電脳世界"
```

Текст должен:

- занимать максимально возможную часть viewport;
- рендериться настоящим CJK-шрифтом, не ASCII-art;
- непрерывно анимироваться выбранным эффектом;
- перестраиваться при resize терминала;
- работать неограниченно долго;
- завершаться по `Ctrl+C`;
- после завершения восстанавливать состояние терминала.

Целевая среда v1:

```text
OS:       Windows 11
Terminal: WezTerm
Python:   CPython 3.11-3.14 x64
```

Runtime prerequisites:

- WezTerm supports truecolor cells and synchronized updates and exposes pane pixel
  and cell dimensions through `wezterm cli list`;
- the Windows x64 release wheel supplies its own versioned FriBiDi runtime and
  activates it before importing Pillow/Raqm;
- the selected CJK font is installed or supplied explicitly.

Rendering core не должен зависеть от WezTerm.

---

## 2. Принципы

Приоритеты:

1. корректный визуальный результат;
2. минимальный объём собственного инфраструктурного кода;
3. использование Pillow, NumPy, stdlib и возможностей терминала;
4. Functional Core / Imperative Shell;
5. изоляция и декомпозиция;
6. DRY;
7. тестируемость;
8. отсутствие преждевременной универсализации.

Не реализовывать самостоятельно font rendering, Unicode shaping, image codecs и функциональность, уже предоставляемую используемыми библиотеками.

---

## 3. Не входит в v1

Не требуются:

- собственный font renderer или shaping engine;
- Qt;
- OpenGL/Vulkan/DirectX;
- GUI или TUI framework;
- plugin system;
- поддержка терминалов кроме WezTerm;
- полноценная японская издательская вёрстка;
- сложный bidirectional layout;
- сохранение GIF/video;
- интерактивное редактирование текста.

---

## 4. CLI

```powershell
mojit "電脳世界"
mojit "警告" -e glitch
mojit "猫" --vertical
mojit "攻殻機動隊" --fps 15
mojit "警告" --seed 42
mojit --list-effects
```

Поддержать:

```text
--help, -h
--effect, -e
--vertical
--horizontal
--font
--fps
--margin
--seed
--config
--list-effects
--debug
```

`--horizontal` явно переопределяет orientation из config.

Текст может поступать через stdin:

```powershell
"少女終末旅行" | mojit
```

Приоритет:

```text
positional argument
↓
stdin
```

stdin читается только при отсутствии positional argument.

В Windows текст из pipe декодируется как UTF-8. Некорректная последовательность
байтов приводит к ошибке ввода до изменения состояния терминала.

Текст должен быть одной строкой длиной от 1 до 4096 Unicode code points, содержать
хотя бы один непробельный символ и не содержать NUL. Для piped stdin удаляется ровно
один завершающий `\r\n` или `\n`; остальные символы и пробелы сохраняются.

Пределы CLI/config:

```text
fps:     1..15
margin:  0 <= margin < 0.5
seed:    signed 64-bit integer
effect:  [a-z][a-z0-9_-]*
```

Ошибки пользовательского ввода завершаются с кодом `2`, непредвиденные ошибки — с
кодом `1`, успешные `--help` и штатное завершение — с кодом `0`. Traceback выводится
только с `--debug`.

`Ctrl+C` является штатным завершением непрерывной animation и возвращает `0`, если
terminal state успешно восстановлен. Любая ошибка cleanup возвращает `1`, включая
cleanup после interrupt. Если runtime и cleanup завершаются ошибкой одновременно,
диагностика должна сохранять обе причины.

---

## 5. Архитектура

Основной поток данных:

```text
Input
  ↓
ResolvedConfig
  ↓
Layout / Typography
  ↓
TextMask
  ↓
Effect / Compositor
  ↓
Frame
  ↓
TerminalBackend
```

Нижележащие слои не обращаются к вышележащим.

### Functional Core

Чистыми должны быть, насколько возможно:

- config resolution;
- layout;
- font-size selection;
- typography calculations;
- effect rendering;
- compositing;
- deterministic randomness.

### Imperative Shell

Side effects ограничены:

- CLI/stdin;
- чтением config;
- загрузкой font resource;
- terminal state;
- resize;
- clock/frame scheduling;
- terminal frame output;
- `Ctrl+C`.

Не вводить интерфейсы и фабрики без фактической необходимости.

---

## 6. Основные модели

Domain/configuration structures по возможности immutable.

```python
Viewport:
    width_px: int
    height_px: int
```

Все layout-расчёты выполняются в пикселях.

```python
TextMask:
    width: int
    height: int
    alpha: ndarray[uint8]   # H × W
```

`TextMask` всегда использует координаты полного viewport:

```text
TextMask.width  == Viewport.width_px
TextMask.height == Viewport.height_px
```

Вне текстовой композиции alpha равна нулю. Отдельного origin у маски в v1 нет.

```python
Frame:
    width: int
    height: int
    rgba: ndarray[uint8]    # H × W × 4
```

```python
RenderContext:
    viewport: Viewport
    frame_index: int
    elapsed_seconds: float
```

Для фиксированного FPS:

```text
elapsed_seconds = frame_index / fps
```

Wall-clock time не должен влиять на deterministic rendering.

---

## 7. Typography

Рендеринг текста выполняется через Pillow/FreeType.

Цвет текста не относится к typography layer.

Результатом typography является `TextMask`.

Font loading, Raqm/FriBiDi capability и запрошенный vertical shaping проверяются до
запуска animation loop и до изменения состояния терминала.

Не выполнять:

- транслитерацию;
- замену Unicode-глифов ASCII-представлением.

---

## 8. Шрифт

Приоритет:

```text
CLI --font
↓
config font
↓
default configured CJK font
```

В v1 `font` представляет путь к font-файлу:

```toml
font = "C:/Windows/Fonts/YuGothB.ttc"
```

Общий Windows font discovery не требуется.

Default path v1:

```text
C:/Windows/Fonts/YuGothB.ttc
```

Шрифт не поставляется вместе с приложением. Если он отсутствует, ошибка должна
предложить установить Windows Japanese Supplemental Fonts либо задать `--font` или
config `font`.

Недоступный или неподдерживаемый шрифт должен приводить к понятной ошибке до запуска animation loop.

---

## 9. Layout

### Horizontal

Для текста:

```text
電脳世界
```

необходимо:

1. определить доступный viewport с учётом margin;
2. построить ограниченный набор вариантов: исходную строку и сбалансированные
   многострочные композиции;
3. для каждого варианта найти максимальный допустимый font size;
4. выбрать вариант с наибольшим font size, предпочитая меньше строк при равенстве;
5. получить bounding box;
6. центрировать композицию;
7. rasterize alpha mask.

Автоматический перенос применяется только к horizontal layout. Он не изменяет
исходный текст, не разделяет combining/emoji sequences и учитывает запрещённые
позиции переноса около японской пунктуации. Публичный ввод по-прежнему остаётся одной
строкой; многострочная композиция является внутренним результатом layout.

### Margin

```toml
margin = 0.08
```

означает резервирование 8% ширины и высоты viewport с каждой стороны.

### Font size

Не использовать линейный перебор.

Найти максимальный размер, удовлетворяющий:

```text
text_width  <= available_width
text_height <= available_height
```

Предпочтительно использовать binary search.

---

## 10. Vertical layout

```powershell
mojit "電脳世界" --vertical
```

Вертикальный режим не реализуется через:

```python
"\n".join(text)
```

Основной путь:

```text
Pillow + libraqm
direction="ttb"
language="ja"
```

если такая конфигурация поддерживается используемым окружением.

Вертикальная пунктуация в первую очередь должна обрабатываться shaping/font machinery.

Отдельный этап fallback-коррекций допускается только для известных проблем:

```text
、
。
「」
『』
ー
（）
```

Такие специальные случаи должны быть локализованы в typography layer и не распространяться по renderer/effects.

---

## 11. Кэширование

`TextMask` пересоздаётся только при изменении параметров, влияющих на typography/layout:

```text
text
font
orientation
viewport
margin
typography options
```

Ключ кэша должен определяться этими значениями.

Typography остаётся чистой.

Mutable cache принадлежит orchestration/application layer, а не typography или effect implementation.

В пределах одного запуска application хранит ровно одну пару
`TypographyKey -> TextMask`. Новый key атомарно заменяет предыдущую пару только после
успешной rasterization и проверки размеров маски. Ошибка создания не удаляет
последнюю валидную запись. Такой cache ограничивает память при многократном resize;
возврат к ранее использованному viewport после промежуточного размера выполняет
повторную rasterization.

---

## 12. Effects

Эффект является чистой функцией:

```python
Effect = Callable[
    [TextMask, RenderContext, EffectConfig],
    Frame
]
```

Регистрация эффектов:

```python
EFFECTS = {
    "neon": render_neon,
    "glitch": render_glitch,
    "chromatic": render_chromatic,
    "pulse": render_pulse,
}
```

Реестр v1 неизменяем и содержит ровно четыре идентификатора: `neon`, `glitch`,
`chromatic`, `pulse`. Неизвестный идентификатор является ошибкой до загрузки шрифта
и изменения состояния терминала. `--list-effects` выводит идентификаторы по одному на
строку в стабильном алфавитном порядке.

`EffectConfig` v1 содержит только signed 64-bit `seed`. Настройки визуального стиля
эффектов не являются пользовательской конфигурацией v1.

Не использовать inheritance-based hierarchy без необходимости.

Эффекты не должны:

- обращаться к терминалу;
- rasterize текст;
- использовать глобальное mutable state.

Визуальная семантика v1:

- `neon` — cyan/blue Gaussian glow с детерминированным breathing;
- `pulse` — центрированное периодическое масштабирование без накопления transform;
- `chromatic` — симметричное смещение RGB channels;
- `glitch` — воспроизводимое горизонтальное смещение полос и разделение channels.

Непрерывная анимация определяется только `RenderContext.elapsed_seconds`. Stochastic
вариация `glitch` определяется только `seed`, фиксированным effect identifier и
`frame_index`.

---

## 13. Детерминированная случайность

Запрещено использовать глобальное состояние:

```python
random
numpy.random
```

Stochastic effect должен получать локальный random state из:

```text
seed
effect identifier
frame_index
```

При одинаковых входных данных:

```text
text
config
seed
frame_index
viewport
```

результат должен быть идентичен.

---

## 14. Compositor

Общие графические операции реализуются один раз:

```text
translate
scale
blur
colorize
alpha_composite
crop
warp
```

Эффекты компонуются из этих операций.

Нельзя независимо реализовывать одинаковые blending/transformation primitives внутри отдельных эффектов.

Растровый контракт v1:

```text
storage:       straight-alpha uint8 sRGB
canvas:        полный viewport
outside:       transparent black
translation:   integer pixels, clipping without wrap-around
scale origin:  viewport center
scale filter:  Pillow LANCZOS
blur:          Pillow GaussianBlur
composition:   standard source-over
```

Публичные compositor operations не изменяют входные `TextMask`/`Frame` и возвращают
новые immutable full-viewport модели. `warp` v1 ограничен горизонтальным смещением
валидированных полос, необходимым эффекту `glitch`; generic affine API не требуется.

---

## 15. Terminal backend

Rendering core ничего не знает о WezTerm.

Backend v1 отвечает за:

```text
получение viewport в пикселях
вывод Frame
управление terminal state
```

Минимальная семантика:

```python
get_viewport() -> Viewport | None
present(frame: Frame) -> None
restore() -> None
```

`None` является только runtime-сигналом кратковременной ошибки измерения. До начала
animation первый вызов обязан вернуть валидный `Viewport`.

Конкретный способ представления `Frame` в WezTerm должен быть выбран один для v1 и
локализован внутри backend.

v1 использует truecolor-ячейки и символы полублока. Backend композитит RGBA-кадр на
чёрный фон, уменьшает его до двух цветовых samples на terminal cell и кодирует
верхний/нижний sample как foreground/background. Первый кадр и изменение cell
geometry очищают и перерисовывают canvas; последующие кадры выводят только серии
изменившихся квантованных ячеек. Каждый present оборачивается в synchronized update.
Внешний subprocess или image protocol в frame path не используется.

До первого terminal-control byte production shell обязан завершить preflight:

```text
PreparedRun полностью валиден
stdout является интерактивным terminal output
WEZTERM_PANE содержит неотрицательный decimal pane ID
bounded wezterm cli list находит ровно этот pane
pixel и cell geometry валидны
```

Успешный exact-pane вызов WezTerm CLI вместе с interactive binary stdout является v1
preflight. Terminal input не читается: stdin может содержать piped text и принадлежит
только input boundary.

Viewport получается bounded-вызовом `wezterm cli list --format json` через отдельный
WezTerm CLI socket с выбором `WEZTERM_PANE`. Polling выполняется независимо от FPS
примерно раз в 250 ms. Первый валидный viewport обязателен; при кратковременном сбое
во время animation сохраняется последнее валидное значение. DPI в layout не
используется.

Resize detection, animation loop, cursor state и обработка `Ctrl+C` принадлежат imperative shell.

`restore()` должен выполняться также при исключении или interrupt.

После успешного `restore()` повторный вызов не выводит дополнительные bytes. После
ошибки cleanup восстановление остаётся retryable и не считается успешным. Ошибка
entry после частичной записи также требует полной cleanup-последовательности.

При hard termination процесса или уже разорванном output
channel cleanup-последовательности доставить невозможно; способ восстановления для
этого ограничения — закрыть затронутый pane.

---

## 16. Animation loop

Цикл:

```text
read viewport
↓
obtain/reuse TextMask
↓
construct RenderContext
↓
render effect
↓
present Frame
↓
advance frame_index
```

При resize:

```text
Viewport changes
↓
TextMask cache miss
↓
layout + rasterization
↓
animation continues
```

Текст не rasterize'ится на каждом кадре.

FPS задаёт целевую частоту presentation и выборки состояния эффекта, но rendering
core не занимается ожиданием или синхронизацией времени. Допустимый диапазон —
`1..15`, default — `8`. Фактическая частота может быть ниже целевой, если render,
resize или terminal output занимают больше одного периода.

Fixed-step scheduling v1:

```text
first frame index:       0
frame deadline(n):       started_at + n / fps
elapsed_seconds(n):      n / fps
late work:               пропустить просроченные indices без catch-up burst
viewport polling:        каждые 0.25 s независимо от FPS
simultaneous deadlines:  сначала viewport poll, затем frame
```

`started_at` читается из monotonic clock после получения первого viewport. Deadlines
вычисляются от абсолютного `started_at`, а не накоплением периода. Если rendering или
presentation заняли несколько периодов, следующий вызов effect получает последний
уже наступивший frame index; промежуточные кадры не рендерятся.

Viewport polling и frame presentation объединены одним синхронным application loop,
но имеют независимые deadlines. После задержки выполняется не более одного poll, а
следующий deadline переносится на первую будущую границу 250 ms. При одновременной
готовности resize проверяется до построения кадра.

Application scheduler является единственным владельцем pacing. Backend не добавляет
паузу после presentation. Значения до `--fps 15` являются best-effort целями и не
гарантируются для больших или дорогих кадров. Scheduling не передаёт wall-clock time
в deterministic rendering.

---

## 17. Конфигурация

CLI имеет приоритет над config:

```text
CLI
↓
config file
↓
defaults
```

Config должен содержать только пользовательские параметры, а не внутренние детали архитектуры.

Допустимые root-level TOML keys:

```text
effect
orientation
font
fps
margin
seed
```

Неизвестные keys, вложенные tables и неверные TOML types являются ошибкой. Размер
файла ограничен 1 MiB, encoding — UTF-8. `debug`, `config` и `list-effects` не являются
TOML-параметрами.

Config выбирается в порядке:

```text
--config PATH
↓
%APPDATA%/mojit/config.toml
↓
без config
```

Явно указанный отсутствующий config является ошибкой; отсутствие default config —
нормальная ситуация. `--config -` запрещён, поскольку stdin зарезервирован для текста.
Относительный `--font` разрешается от current working directory, относительный `font`
из TOML — от директории config-файла.

Defaults v1:

```text
effect:       neon
orientation:  horizontal
font:         C:/Windows/Fonts/YuGothB.ttc
fps:          8
margin:       0.08
seed:         0
debug:        false
```

---

## 18. Критерии готовности v1

Команда:

```powershell
mojit "電脳世界"
```

должна:

- корректно отображать CJK-текст в WezTerm;
- автоматически выбирать максимальный размер;
- поддерживать horizontal и vertical layout;
- поддерживать несколько эффектов;
- корректно реагировать на resize;
- обеспечивать deterministic `--seed`;
- работать длительное время без накопления ресурсов;
- корректно восстанавливать terminal state после `Ctrl+C` и ошибок.

Архитектурная граница v1:

```text
pure rendering core
+
small imperative shell
+
single WezTerm backend
```

Без универсализации сверх этого.
