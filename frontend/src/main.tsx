import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowDownToLine,
  ArrowLeft,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  Box,
  CalendarDays,
  Camera,
  Check,
  CheckCircle2,
  ChevronRight,
  ClipboardCheck,
  Clock3,
  FileText,
  History as HistoryIcon,
  LayoutDashboard,
  LogOut,
  MapPin,
  Plus,
  QrCode,
  Search,
  Settings2,
  ShieldCheck,
  Stethoscope,
  Trash2,
  TriangleAlert,
  X,
} from "lucide-react";
import { api, ApiError, dateLabel, reasons, setCSRF } from "./api";
import type {
  Group,
  History,
  Inspection,
  Item,
  Kit,
  Template,
  User,
} from "./api";
import "./styles.css";

type Page = "overview" | "kits" | "templates" | "history" | "analytics";
const titles: Record<Page, string> = {
  overview: "Обзор",
  kits: "Аптечки",
  templates: "Шаблоны",
  history: "История проверок",
  analytics: "Аналитика",
};
const statusLabel: Record<string, string> = {
  OK: "Без замечаний",
  PROBLEM: "Есть замечания",
  NEVER_CHECKED: "Нет проверок",
  CURRENT: "Проверка актуальна",
  OVERDUE: "Пора проверить",
};
function Badge({ value }: { value: string }) {
  return (
    <span className={`badge ${value.toLowerCase()}`}>
      {value === "OK" ? (
        <CheckCircle2 size={13} />
      ) : value === "PROBLEM" ? (
        <TriangleAlert size={13} />
      ) : (
        <Clock3 size={13} />
      )}{" "}
      {statusLabel[value] || value}
    </span>
  );
}
function Empty({ title, detail }: { title: string; detail: string }) {
  return (
    <div className="empty">
      <ClipboardCheck size={32} />
      <h3>{title}</h3>
      <p>{detail}</p>
    </div>
  );
}
function Logo() {
  return (
    <div className="logo">
      <span className="logo-icon">
        <Plus size={25} strokeWidth={3} />
      </span>
      <span>
        medkit<span className="logo-dot">.</span>
        <small>INSPECTOR</small>
      </span>
    </div>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null),
    [loading, setLoading] = useState(true),
    [kits, setKits] = useState<Kit[]>([]),
    [templates, setTemplates] = useState<Template[]>([]),
    [page, setPage] = useState<Page>("overview"),
    [kit, setKit] = useState<Kit | null>(null),
    [inspection, setInspection] = useState<Inspection | null>(null),
    [error, setError] = useState(""),
    [notice, setNotice] = useState(""),
    [busy, setBusy] = useState(false),
    [kitEditor, setKitEditor] = useState<Kit | "new" | null>(null),
    [templateEditor, setTemplateEditor] = useState<Template | "new" | null>(
      null,
    ),
    [qr, setQr] = useState<Kit | null>(null),
    [dirty, setDirty] = useState(false);
  const showError = (e: unknown) =>
    setError(e instanceof Error ? e.message : "Не удалось выполнить действие.");
  async function refresh() {
    const [k, t] = await Promise.all([
      api<Kit[]>("/kits"),
      api<Template[]>("/templates"),
    ]);
    setKits(k);
    setTemplates(t);
    setKit((prev) => (prev ? k.find((i) => i.id === prev.id) || prev : null));
    return k;
  }
  async function enter(u: User) {
    setNotice("");
    setCSRF(u.csrf_token);
    setUser(u);
    const k = await refresh();
    const match = window.location.pathname.match(/^\/q\/([^/]+)$/);
    if (match) {
      const selected = k.find((i) => i.public_code === match[1]);
      if (selected) setKit(selected);
      else
        setKit(await api<Kit>(`/kits/by-code/${encodeURIComponent(match[1])}`));
    }
  }
  useEffect(() => {
    api<User>("/auth/session")
      .then(enter)
      .catch((e) => {
        if (!(e instanceof ApiError && e.status === 401)) showError(e);
      })
      .finally(() => setLoading(false));
    const expired = () => {
      setCSRF("");
      setUser(null);
      setKits([]);
      setInspection(null);
      setKit(null);
      setNotice(
        "Сессия завершилась. Войдите снова; сохранённый черновик останется доступен.",
      );
    };
    window.addEventListener("medkit-session-expired", expired);
    return () => window.removeEventListener("medkit-session-expired", expired);
  }, []);
  useEffect(() => {
    const before = (e: BeforeUnloadEvent) => {
      if (dirty) {
        e.preventDefault();
        e.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", before);
    return () => window.removeEventListener("beforeunload", before);
  }, [dirty]);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 6000);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  function safeLeave() {
    if (
      dirty &&
      !window.confirm("Есть несохранённые изменения. Покинуть страницу?")
    )
      return false;
    setDirty(false);
    return true;
  }
  function navigate(next: Page) {
    if (!safeLeave()) return;
    setPage(next);
    setKit(null);
    setInspection(null);
    window.history.replaceState({}, "", "/");
    setError("");
  }
  async function openKit(k: Kit) {
    if (!safeLeave()) return;
    setKit(k);
    setInspection(null);
    setPage("kits");
    window.history.replaceState({}, "", `/q/${k.public_code}`);
  }
  async function run(task: () => Promise<void>) {
    setError("");
    setBusy(true);
    try {
      await task();
    } catch (e) {
      showError(e);
    } finally {
      setBusy(false);
    }
  }
  async function start(k: Kit) {
    await run(async () => {
      const i = await api<Inspection>(`/kits/${k.id}/inspections`, "POST");
      setInspection(i);
      await refresh();
    });
  }
  async function finish() {
    if (!inspection || !safeLeave()) return;
    await run(async () => {
      const i = await api<Inspection>(
        `/inspections/${inspection.id}/complete`,
        "POST",
        { expected_revision: inspection.revision },
      );
      setInspection(i);
      setNotice("Проверка завершена. Результат и отчёт сохранены.");
      await refresh();
    });
  }
  async function cancel() {
    if (!inspection) return;
    const reason = window.prompt("Причина отмены проверки (обязательно):");
    if (!reason?.trim()) return;
    await run(async () => {
      await api(`/inspections/${inspection.id}/cancel`, "POST", {
        expected_revision: inspection.revision,
        reason,
      });
      setInspection(null);
      setDirty(false);
      await refresh();
      setNotice("Черновик отменён.");
    });
  }
  if (loading)
    return (
      <div className="initial">
        <Logo />
        <p>Открываем рабочее пространство…</p>
      </div>
    );
  if (!user)
    return (
      <Login
        onLogin={(u) => run(() => enter(u))}
        error={error}
        notice={notice}
        busy={busy}
      />
    );
  const active = kits.filter((k) => !k.archived),
    problems = active.filter((k) => k.last_result === "PROBLEM"),
    due = active.filter(
      (k) => k.freshness === "OVERDUE" || k.freshness === "NEVER_CHECKED",
    );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Logo />
        <div className="workspace">
          <div className="workspace-icon">
            <Stethoscope size={19} />
          </div>
          <div>
            <strong>Рабочее пространство</strong>
            <small>{user.organization.name}</small>
          </div>
        </div>
        <div className="nav-caption">УПРАВЛЕНИЕ</div>
        <nav>
          {(
            [
              { id: "overview", icon: LayoutDashboard },
              { id: "kits", icon: Box },
              { id: "history", icon: HistoryIcon },
              { id: "templates", icon: FileText },
              { id: "analytics", icon: BarChart3 },
            ] as const
          ).map((n) => (
            <button
              key={n.id}
              className={`nav-item ${page === n.id ? "active" : ""}`}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={19} />
              {titles[n.id]}
              {n.id === "kits" && (
                <span className="nav-count">{active.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-note">
          <ShieldCheck size={23} />
          <strong>Проверка — это забота</strong>
          <p>Контролируйте состав и сроки, чтобы важное было под рукой.</p>
          <span>
            Учебный MVP <span className="tiny-dot" />
          </span>
        </div>
        <div className="user-block">
          <div className="avatar">
            {user.display_name
              .split(" ")
              .slice(0, 2)
              .map((s) => s[0])
              .join("")}
          </div>
          <div>
            <strong>{user.display_name}</strong>
            <small>
              {user.role === "ADMIN" ? "Администратор" : "Инспектор"}
            </small>
          </div>
          <button
            className="icon-button"
            title="Выйти"
            onClick={() => {
              if (safeLeave())
                run(async () => {
                  await api("/auth/logout", "POST");
                  setUser(null);
                  setCSRF("");
                  setKits([]);
                  setInspection(null);
                  setKit(null);
                });
            }}
          >
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <main className="main">
        <header className="topbar">
          <div className="breadcrumb">
            Рабочее пространство <ChevronRight size={14} />
            <span>{titles[page]}</span>
          </div>
          <span className="top-date">
            <CalendarDays size={16} />
            {new Intl.DateTimeFormat("ru-RU", {
              day: "numeric",
              month: "long",
              year: "numeric",
              timeZone: user.organization.timezone,
            }).format(new Date())}
          </span>
        </header>
        <div className="page-content">
          {error && (
            <div className="alert error" role="alert">
              <TriangleAlert size={20} />
              <span>{error}</span>
              <button aria-label="Закрыть ошибку" onClick={() => setError("")}>
                <X size={18} />
              </button>
            </div>
          )}
          {notice && (
            <div className="alert success" role="status">
              <CheckCircle2 size={20} />
              <span>{notice}</span>
              <button
                aria-label="Закрыть уведомление"
                onClick={() => setNotice("")}
              >
                <X size={18} />
              </button>
            </div>
          )}
          {inspection ? (
            <>
              <button
                className="back-link"
                onClick={() => {
                  if (safeLeave()) setInspection(null);
                }}
              >
                <ArrowLeft size={16} /> К аптечке
              </button>
              {inspection.lifecycle === "DRAFT" ? (
                <InspectionEditor
                  key={inspection.id}
                  inspection={inspection}
                  setInspection={setInspection}
                  dirty={dirty}
                  setDirty={setDirty}
                  onError={showError}
                  onComplete={finish}
                  onCancel={cancel}
                  busy={busy}
                />
              ) : (
                <Result inspection={inspection} />
              )}
            </>
          ) : kit ? (
            <KitDetail
              kit={kit}
              user={user}
              busy={busy}
              onStart={() => start(kit)}
              onBack={() => navigate("kits")}
              onQR={() => setQr(kit)}
              onEdit={() => setKitEditor(kit)}
              onArchive={() => {
                if (
                  window.confirm(
                    "Перенести аптечку в архив? История сохранится.",
                  )
                )
                  run(async () => {
                    await api(`/kits/${kit.id}/archive`, "POST");
                    await refresh();
                    setNotice("Аптечка перенесена в архив.");
                  });
              }}
              onInspection={(i) => setInspection(i)}
              onError={showError}
              onCancelDraft={() => {
                const reason = window.prompt(
                  "Причина отмены чужого черновика:",
                );
                if (!reason?.trim()) return;
                run(async () => {
                  await api(`/inspections/${kit.draft_id}/cancel`, "POST", {
                    expected_revision: kit.draft_revision,
                    reason,
                  });
                  await refresh();
                });
              }}
            />
          ) : (
            <>
              <div className="page-heading">
                <div>
                  <div className="eyebrow">MEDKIT INSPECTOR</div>
                  <h1>
                    {page === "overview"
                      ? "Аптечки под контролем"
                      : titles[page]}
                  </h1>
                  <p>
                    {page === "overview"
                      ? "Всё, что нужно для своевременной проверки."
                      : page === "kits"
                        ? "Состав, сроки и результаты проверок в одном месте."
                        : page === "templates"
                          ? "Единые чек-листы для каждой аптечки."
                          : page === "analytics"
                            ? "Текущее состояние по сохранённым результатам проверок."
                            : "Каждая проверка сохраняется вместе с исходными данными."}
                  </p>
                </div>
                {user.role === "ADMIN" &&
                  (page === "overview" || page === "kits") && (
                    <button
                      className="primary"
                      onClick={() => setKitEditor("new")}
                    >
                      <Plus size={18} />
                      Добавить аптечку
                    </button>
                  )}
                {user.role === "ADMIN" && page === "templates" && (
                  <button
                    className="primary"
                    onClick={() => setTemplateEditor("new")}
                  >
                    <Plus size={18} />
                    Новый шаблон
                  </button>
                )}
              </div>
              {(page === "overview" || page === "analytics") && (
                <div className="stats-grid">
                  <Stat
                    label="Всего аптечек"
                    value={active.length}
                    detail="Активных в организации"
                    icon={<Box size={21} />}
                    tone="green"
                  />
                  <Stat
                    label="Без замечаний"
                    value={active.filter((k) => k.last_result === "OK").length}
                    detail="По последней проверке"
                    icon={<ShieldCheck size={21} />}
                    tone="green"
                  />
                  <Stat
                    label="Есть замечания"
                    value={problems.length}
                    detail="Нужно обратить внимание"
                    icon={<TriangleAlert size={21} />}
                    tone="orange"
                  />
                  <Stat
                    label="Пора проверить"
                    value={due.length}
                    detail="Срок подошёл или нет истории"
                    icon={<Clock3 size={21} />}
                    tone="purple"
                  />
                </div>
              )}
              {page === "overview" && (
                <>
                  <section className="hero">
                    <div className="hero-copy">
                      <span className="hero-tag">
                        <span className="tiny-dot" /> НАЧНИТЕ С ПРОСТОГО
                      </span>
                      <h2>
                        Одна проверка.
                        <br />
                        Меньше поводов для тревоги.
                      </h2>
                      <p>
                        Откройте аптечку, сверьте содержимое и сроки.
                        <br />
                        Список замечаний и отчёт мы соберём сами.
                      </p>
                      <button onClick={() => navigate("kits")}>
                        Перейти к аптечкам <ArrowRight size={17} />
                      </button>
                    </div>
                    <div className="hero-art" aria-hidden="true">
                      <div className="orbit orbit-one" />
                      <div className="orbit orbit-two" />
                      <div className="medical-case">
                        <div className="case-handle" />
                        <div className="case-cross">
                          <Plus size={64} strokeWidth={5} />
                        </div>
                        <div className="case-line" />
                      </div>
                      <div className="art-check">
                        <Check size={27} />
                      </div>
                      <div className="art-label">
                        <ShieldCheck size={17} /> Всё на своём месте
                      </div>
                      <span className="art-spark">✦</span>
                    </div>
                  </section>
                  <div className="section-heading">
                    <div>
                      <h2>
                        Требуют внимания{" "}
                        <span className="count-pill">
                          {due.length +
                            problems.filter((k) => !due.includes(k)).length}
                        </span>
                      </h2>
                      <p>
                        Сначала — аптечки с замечаниями и просроченным обходом
                      </p>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => navigate("kits")}
                    >
                      Все аптечки <ArrowUpRight size={16} />
                    </button>
                  </div>
                  <div className="kit-grid">
                    {active
                      .filter((k) => problems.includes(k) || due.includes(k))
                      .slice(0, 3)
                      .map((k) => (
                        <KitCard
                          key={k.id}
                          kit={k}
                          onOpen={() => openKit(k)}
                          onQR={() => setQr(k)}
                        />
                      ))}
                  </div>
                  {!due.length && !problems.length && (
                    <Empty
                      title="Всё под контролем"
                      detail="Аптечки проверены, замечаний по чек-листам не найдено."
                    />
                  )}
                  <div className="bottom-note">
                    <Activity size={16} />
                    <span>
                      Результат относится к дате проверки. Расход содержимого
                      после неё не отслеживается.
                    </span>
                  </div>
                </>
              )}
              {page === "kits" && (
                <KitList kits={kits} onOpen={openKit} onQR={setQr} />
              )}
              {page === "templates" && (
                <div className="template-grid">
                  {templates.map((t) => (
                    <article className="template-card" key={t.id}>
                      <div className="template-top">
                        <span className="kit-icon">
                          <ClipboardCheck size={23} />
                        </span>
                        <span className="badge neutral">
                          Версия {t.version}
                        </span>
                      </div>
                      <h2>{t.name}</h2>
                      <p>
                        {t.items.length} позиций ·{" "}
                        {t.items.filter((i) => i.requires_expiry).length} с
                        контролем срока
                      </p>
                      <ul>
                        {t.items.map((i) => (
                          <li key={i.id}>
                            <span>{i.name}</span>
                            <strong>
                              {i.required_qty} {i.unit}
                            </strong>
                          </li>
                        ))}
                      </ul>
                      {user.role === "ADMIN" && (
                        <button
                          className="secondary full"
                          onClick={() => setTemplateEditor(t)}
                        >
                          <Settings2 size={16} /> Создать новую версию
                        </button>
                      )}
                    </article>
                  ))}
                  {!templates.length && (
                    <Empty
                      title="Пока нет шаблонов"
                      detail="Администратор может создать первый чек-лист."
                    />
                  )}
                </div>
              )}
              {page === "history" && (
                <AllHistory
                  kits={kits}
                  onOpen={(i) => setInspection(i)}
                  onError={showError}
                />
              )}
              {page === "analytics" && (
                <Analytics kits={active} onOpen={openKit} />
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              medkit. <span>Инвентарная проверка аптечек</span>
            </span>
            <span>MVP · 2026</span>
          </footer>
        </div>
      </main>
      {qr && (
        <Modal title="QR-код аптечки" onClose={() => setQr(null)}>
          <div className="qr-content">
            <h3>{qr.name}</h3>
            <p>{qr.location}</p>
            <img src={`/api/v1/kits/${qr.id}/qr`} alt={`QR-код ${qr.name}`} />
            <p>
              Сканируйте камерой телефона.
              <br />
              Для доступа потребуется вход.
            </p>
            <a
              className="primary"
              href={`/api/v1/kits/${qr.id}/qr`}
              download={`medkit-${qr.id}-qr.png`}
            >
              <ArrowDownToLine size={17} />
              Скачать QR
            </a>
          </div>
        </Modal>
      )}
      {kitEditor && (
        <KitForm
          kit={kitEditor}
          templates={templates}
          onClose={() => setKitEditor(null)}
          onSave={async (body) => {
            await api(
              kitEditor === "new" ? "/kits" : `/kits/${kitEditor.id}`,
              kitEditor === "new" ? "POST" : "PATCH",
              body,
            );
            await refresh();
            setKitEditor(null);
            setNotice("Аптечка сохранена.");
          }}
        />
      )}
      {templateEditor && (
        <TemplateForm
          template={templateEditor}
          onClose={() => setTemplateEditor(null)}
          onSave={async (body) => {
            await api(
              templateEditor === "new"
                ? "/templates"
                : `/templates/${templateEditor.id}/versions`,
              "POST",
              body,
            );
            await refresh();
            setTemplateEditor(null);
            setNotice(
              "Новая версия шаблона сохранена. История проверок не изменена.",
            );
          }}
        />
      )}
    </div>
  );
}
function Login({
  onLogin,
  error,
  notice,
  busy,
}: {
  onLogin: (u: User) => Promise<void>;
  error: string;
  notice: string;
  busy: boolean;
}) {
  const [email, setEmail] = useState(""),
    [password, setPassword] = useState(""),
    [localError, setError] = useState(""),
    [loading, setLoading] = useState(false);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(
        await api<User>("/auth/login", "POST", { email, password }),
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  return (
    <div className="login-page">
      <div className="login-aside">
        <Logo />
        <div>
          <span className="hero-tag">ПОРЯДОК В ВАЖНОМ</span>
          <h1>
            Уверенность
            <br />
            начинается
            <br />с проверки<span>.</span>
          </h1>
          <p>
            Аптечки, сроки и история проверок —<br />в одном рабочем
            пространстве.
          </p>
          <div className="login-illustration">
            <Plus size={100} strokeWidth={3} />
            <ShieldCheck size={56} />
          </div>
        </div>
        <small>MedKit Inspector · Учебный проект</small>
      </div>
      <div className="login-main">
        <form onSubmit={submit}>
          <span className="kit-icon">
            <ShieldCheck size={24} />
          </span>
          <h2>Добро пожаловать</h2>
          <p>Войдите в рабочее пространство организации</p>
          {(error || localError) && (
            <div className="alert error" role="alert">
              {localError || error}
            </div>
          )}
          {notice && <div className="alert success">{notice}</div>}
          <label>
            Электронная почта
            <input
              autoComplete="username"
              type="email"
              required
              value={email}
              placeholder="name@company.ru"
              onChange={(e) => setEmail(e.target.value)}
            />
          </label>
          <label>
            Пароль
            <input
              autoComplete="current-password"
              type="password"
              required
              maxLength={128}
              value={password}
              placeholder="Введите пароль"
              onChange={(e) => setPassword(e.target.value)}
            />
          </label>
          <button className="primary full" disabled={loading || busy}>
            {loading ? "Входим…" : "Войти"}
            <ArrowRight size={17} />
          </button>
          <div className="demo-hint">
            <strong>Демонстрационный стенд</strong>
            <span>Если выполнена команда seed-demo:</span>
            <code>admin@medkit.demo</code>
            <code>MedkitDemo2026!</code>
            <button
              type="button"
              onClick={() => {
                setEmail("admin@medkit.demo");
                setPassword("MedkitDemo2026!");
              }}
            >
              Заполнить демоданные <ArrowUpRight size={13} />
            </button>
          </div>
          <small className="login-foot">
            Аккаунт выдаёт оператор вашей организации.
          </small>
        </form>
      </div>
    </div>
  );
}
function Stat({
  label,
  value,
  detail,
  icon,
  tone,
}: {
  label: string;
  value: number;
  detail: string;
  icon: React.ReactNode;
  tone: string;
}) {
  return (
    <div className="stat">
      <div className="stat-top">
        <span>{label}</span>
        <span className={`stat-icon ${tone}`}>{icon}</span>
      </div>
      <strong>{value.toString().padStart(2, "0")}</strong>
      <small>{detail}</small>
    </div>
  );
}
function KitCard({
  kit: k,
  onOpen,
  onQR,
}: {
  kit: Kit;
  onOpen: () => void;
  onQR: () => void;
}) {
  return (
    <article className={`kit-card ${k.archived ? "archived" : ""}`}>
      <div className="kit-card-top">
        <span className="kit-icon">
          <Plus size={23} />
        </span>
        <button
          className="icon-button"
          title={`QR-код: ${k.name}`}
          onClick={onQR}
        >
          <QrCode size={19} />
        </button>
      </div>
      <h3>
        <button className="title-button" onClick={onOpen}>
          {k.name}
        </button>
      </h3>
      <p className="location">
        <MapPin size={14} />
        {k.location}
      </p>
      <div className="kit-badges">
        <Badge value={k.last_result} />
        {k.archived ? (
          <span className="badge neutral">В архиве</span>
        ) : (
          k.freshness === "OVERDUE" && <Badge value="OVERDUE" />
        )}
      </div>
      <div className="kit-card-meta">
        <span>Последняя проверка</span>
        <strong>{dateLabel(k.last_completed_at)}</strong>
      </div>
      {k.warnings.length > 0 && (
        <p className="warning-text">
          {k.warnings
            .map((w) =>
              w === "CONFIG_CHANGED"
                ? "Обновлён шаблон"
                : "Срок истёк после проверки",
            )
            .join(" · ")}
        </p>
      )}
      <button className="card-action" onClick={onOpen}>
        {k.draft_id
          ? "Продолжить проверку"
          : k.archived
            ? "Открыть историю"
            : "Открыть аптечку"}
        <ArrowRight size={16} />
      </button>
    </article>
  );
}
function KitList({
  kits,
  onOpen,
  onQR,
}: {
  kits: Kit[];
  onOpen: (k: Kit) => void;
  onQR: (k: Kit) => void;
}) {
  const [search, setSearch] = useState(""),
    [filter, setFilter] = useState("all");
  const selected = kits.filter(
    (k) =>
      (filter === "archive" ? k.archived : !k.archived) &&
      (filter !== "problem" || k.last_result === "PROBLEM") &&
      (filter !== "due" ||
        k.freshness === "OVERDUE" ||
        k.freshness === "NEVER_CHECKED") &&
      `${k.name} ${k.location}`.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="list-toolbar">
        <div className="tabs">
          {[
            ["all", "Все аптечки"],
            ["problem", "С замечаниями"],
            ["due", "Пора проверить"],
            ["archive", "Архив"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={filter === id ? "selected" : ""}
              onClick={() => setFilter(id)}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="search">
          <Search size={17} />
          <input
            aria-label="Поиск аптечек"
            placeholder="Название или локация"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </label>
      </div>
      <div className="kit-grid">
        {selected.map((k) => (
          <KitCard
            key={k.id}
            kit={k}
            onOpen={() => onOpen(k)}
            onQR={() => onQR(k)}
          />
        ))}
      </div>
      {selected.length === 0 && (
        <Empty
          title="Аптечки не найдены"
          detail="Измените поиск или добавьте новую аптечку."
        />
      )}
    </>
  );
}
function KitDetail({
  kit: k,
  user,
  busy,
  onStart,
  onBack,
  onQR,
  onEdit,
  onArchive,
  onInspection,
  onError,
  onCancelDraft,
}: {
  kit: Kit;
  user: User;
  busy: boolean;
  onStart: () => void;
  onBack: () => void;
  onQR: () => void;
  onEdit: () => void;
  onArchive: () => void;
  onInspection: (i: Inspection) => void;
  onError: (e: unknown) => void;
  onCancelDraft: () => void;
}) {
  return (
    <>
      <button className="back-link" onClick={onBack}>
        <ArrowLeft size={16} /> Все аптечки
      </button>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            АПТЕЧКА #{k.id.toString().padStart(3, "0")}
          </div>
          <h1>{k.name}</h1>
          <p>
            <MapPin size={15} />
            {k.location}
          </p>
        </div>
        <div className="button-row">
          <button className="secondary" onClick={onQR}>
            <QrCode size={17} />
            QR-код
          </button>
          {!k.archived && (
            <button
              className="primary"
              disabled={busy || (!!k.draft_id && k.draft_owner_id !== user.id)}
              onClick={onStart}
            >
              <ClipboardCheck size={17} />
              {k.draft_id ? "Продолжить проверку" : "Начать проверку"}
            </button>
          )}
        </div>
      </div>
      <div className="detail-summary">
        <div>
          <small>Последний результат</small>
          <Badge value={k.last_result} />
          <span>{dateLabel(k.last_completed_at)}</span>
        </div>
        <div>
          <small>Следующая проверка</small>
          <strong>
            {k.archived
              ? "В архиве"
              : k.due_date
                ? dateLabel(k.due_date)
                : "Проведите первую проверку"}
          </strong>
          <span>{!k.archived && statusLabel[k.freshness]}</span>
        </div>
        <div>
          <small>Чек-лист</small>
          <strong>{k.template_name}</strong>
          <span>
            Версия {k.template_version} · каждые {k.interval_days} дней
          </span>
        </div>
      </div>
      {k.warnings.map((w) => (
        <div className="alert warning" key={w}>
          <TriangleAlert size={18} />
          {w === "CONFIG_CHANGED"
            ? "Состав шаблона изменился. Старый результат сохранён; проведите новую проверку."
            : "После последней проверки истёк срок одной из групп. Проверьте аптечку заново."}
        </div>
      ))}
      {k.draft_id && k.draft_owner_id !== user.id && (
        <div className="alert warning">
          Другой сотрудник уже начал проверку.
          {user.role === "ADMIN" && (
            <button className="text-button" onClick={onCancelDraft}>
              Отменить черновик
            </button>
          )}
        </div>
      )}
      <div className="section-heading">
        <div>
          <h2>История проверок</h2>
          <p>Сохранённые результаты и отчёты этой аптечки</p>
        </div>
        {user.role === "ADMIN" && !k.archived && (
          <div className="button-row">
            <button className="text-button" onClick={onEdit}>
              <Settings2 size={15} /> Изменить
            </button>
            <button className="text-button danger" onClick={onArchive}>
              В архив
            </button>
          </div>
        )}
      </div>
      <HistoryTable
        key={`${k.id}-${k.draft_id}`}
        kitId={k.id}
        onOpen={onInspection}
        onError={onError}
      />
      <div className="bottom-note">
        <ShieldCheck size={16} />
        Результат относится к дате проверки. Расход после неё не отслеживается.
      </div>
    </>
  );
}
function HistoryTable({
  kitId,
  onOpen,
  onError,
}: {
  kitId: number;
  onOpen: (i: Inspection) => void;
  onError: (e: unknown) => void;
}) {
  const [history, setHistory] = useState<History | null>(null),
    [page, setPage] = useState(1),
    [cancelled, setCancelled] = useState(false);
  useEffect(() => {
    setHistory(null);
    api<History>(
      `/kits/${kitId}/inspections?page=${page}&cancelled=${cancelled}`,
    )
      .then(setHistory)
      .catch(onError);
  }, [kitId, page, cancelled]);
  return (
    <>
      <div className="tabs history-tabs">
        <button
          className={!cancelled ? "selected" : ""}
          onClick={() => {
            setPage(1);
            setCancelled(false);
          }}
        >
          Завершённые
        </button>
        <button
          className={cancelled ? "selected" : ""}
          onClick={() => {
            setPage(1);
            setCancelled(true);
          }}
        >
          Отменённые
        </button>
      </div>
      {!history ? (
        <p className="muted">Загружаем историю…</p>
      ) : !history.items.length ? (
        <Empty
          title="Проверок пока нет"
          detail="После завершения здесь появятся результат и PDF-отчёт."
        />
      ) : (
        <>
          <div className="history-list">
            {history.items.map((i) => (
              <button
                className="history-row"
                key={i.id}
                onClick={() => onOpen(i)}
              >
                <span className="history-symbol">
                  <ClipboardCheck size={20} />
                </span>
                <span>
                  <strong>Проверка #{i.id}</strong>
                  <small>
                    {dateLabel(i.completed_at || i.started_at)} ·{" "}
                    {i.snapshot.inspector_name}
                  </small>
                </span>
                {i.lifecycle === "CANCELLED" ? (
                  <span className="badge neutral">Отменена</span>
                ) : (
                  <Badge value={i.result!} />
                )}
                <ChevronRight size={18} />
              </button>
            ))}
          </div>
          <div className="pagination">
            <button
              className="secondary"
              disabled={page === 1}
              onClick={() => setPage(page - 1)}
            >
              Назад
            </button>
            <span>Страница {page}</span>
            <button
              className="secondary"
              disabled={!history.has_next}
              onClick={() => setPage(page + 1)}
            >
              Далее
            </button>
          </div>
        </>
      )}
    </>
  );
}
function AllHistory({
  kits,
  onOpen,
  onError,
}: {
  kits: Kit[];
  onOpen: (i: Inspection) => void;
  onError: (e: unknown) => void;
}) {
  const [id, setId] = useState(kits[0]?.id || 0);
  return (
    <>
      <label className="history-select">
        Аптечка
        <select value={id} onChange={(e) => setId(Number(e.target.value))}>
          {kits.map((k) => (
            <option key={k.id} value={k.id}>
              {k.name}
              {k.archived ? " · архив" : ""}
            </option>
          ))}
        </select>
      </label>
      {id ? (
        <HistoryTable key={id} kitId={id} onOpen={onOpen} onError={onError} />
      ) : (
        <Empty
          title="История пуста"
          detail="Сначала создайте аптечку и проведите проверку."
        />
      )}
    </>
  );
}
function InspectionEditor({
  inspection: i,
  setInspection,
  dirty,
  setDirty,
  onError,
  onComplete,
  onCancel,
  busy,
}: {
  inspection: Inspection;
  setInspection: (i: Inspection) => void;
  dirty: boolean;
  setDirty: (v: boolean) => void;
  onError: (e: unknown) => void;
  onComplete: () => void;
  onCancel: () => void;
  busy: boolean;
}) {
  const [index, setIndex] = useState(
      Math.max(
        0,
        i.items.findIndex((it) => !it.checked_at),
      ),
    ),
    [saving, setSaving] = useState(false);
  const checked = i.items.filter((it) => it.checked_at).length;
  async function save(body: unknown) {
    setSaving(true);
    try {
      const next = await api<Inspection>(
        `/inspections/${i.id}/items/${i.items[index].id}`,
        "PUT",
        { ...(body as object), expected_revision: i.revision },
      );
      setInspection(next);
      setDirty(false);
      if (index < i.items.length - 1) setIndex(index + 1);
    } catch (e) {
      onError(e);
    } finally {
      setSaving(false);
    }
  }
  async function reload() {
    if (
      dirty &&
      !window.confirm(
        "Загрузить сохранённый черновик? Несохранённые правки будут потеряны.",
      )
    )
      return;
    try {
      setInspection(await api<Inspection>(`/inspections/${i.id}`));
      setDirty(false);
    } catch (e) {
      onError(e);
    }
  }
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">ПРОВЕРКА #{i.id} · ЧЕРНОВИК</div>
          <h1>{i.snapshot.kit_name}</h1>
          <p>
            {i.snapshot.location} · Шаблон v{i.snapshot.template_version}
          </p>
        </div>
        <div className={`save-state ${dirty ? "unsaved" : ""}`}>
          {dirty ? <Clock3 size={15} /> : <CheckCircle2 size={15} />}{" "}
          {dirty ? "Есть несохранённые изменения" : "Все изменения сохранены"}
        </div>
      </div>
      <div className="inspection-layout">
        <aside className="checklist-nav">
          <div className="progress-heading">
            <strong>Чек-лист</strong>
            <span>
              {checked} / {i.items.length}
            </span>
          </div>
          <progress value={checked} max={i.items.length} />
          {i.items.map((item, n) => (
            <button
              className={`checklist-item ${index === n ? "selected" : ""}`}
              key={item.id}
              onClick={() => {
                if (
                  dirty &&
                  !window.confirm("Перейти к другой позиции без сохранения?")
                )
                  return;
                setDirty(false);
                setIndex(n);
              }}
            >
              <span className={item.checked_at ? "step checked" : "step"}>
                {item.checked_at ? <Check size={13} /> : n + 1}
              </span>
              <span>
                {item.name}
                <small>
                  {item.required_qty} {item.unit} по шаблону
                </small>
              </span>
            </button>
          ))}
          <button className="text-button" onClick={reload}>
            Обновить черновик с сервера
          </button>
        </aside>
        <ItemEditor
          key={`${i.id}-${index}-${i.revision}`}
          item={i.items[index]}
          inspectionId={i.id}
          index={index}
          total={i.items.length}
          onDirty={() => setDirty(true)}
          onSave={save}
          busy={saving}
          onError={onError}
        />
      </div>
      <div className="inspection-bottom">
        <button
          className="text-button danger"
          disabled={busy || saving}
          onClick={onCancel}
        >
          Отменить проверку
        </button>
        <div>
          <span className="muted">
            {checked === i.items.length
              ? "Все позиции подтверждены"
              : `Осталось подтвердить: ${i.items.length - checked}`}
          </span>
          <button
            className="primary"
            disabled={dirty || checked !== i.items.length || busy || saving}
            onClick={onComplete}
          >
            <CheckCircle2 size={18} />
            {busy ? "Сохраняем результат…" : "Завершить проверку"}
          </button>
        </div>
      </div>
    </>
  );
}
function ItemEditor({
  item,
  inspectionId,
  index,
  total,
  onDirty,
  onSave,
  busy,
  onError,
}: {
  item: Item;
  inspectionId: number;
  index: number;
  total: number;
  onDirty: () => void;
  onSave: (body: unknown) => Promise<void>;
  busy: boolean;
  onError: (e: unknown) => void;
}) {
  const [qty, setQty] = useState(
      item.actual_qty === null ? "" : String(item.actual_qty),
    ),
    [groups, setGroups] = useState<Group[]>(
      item.groups.map((g) => ({
        ...g,
        confirmed: g.expiry_state === "KNOWN",
        month_end_confirmed: g.policy === "MONTH_END_V1",
      })),
    ),
    [confirmed, setConfirmed] = useState(!!item.checked_at),
    [ocrBusy, setOCRBusy] = useState<number | null>(null),
    [ocrMessage, setOCRMessage] = useState("");
  function changeGroup(n: number, patch: Partial<Group>) {
    setGroups((prev) => prev.map((g, j) => (j === n ? { ...g, ...patch } : g)));
    onDirty();
  }
  function updateQty(value: string) {
    setQty(value);
    setConfirmed(false);
    if (value === "0") setGroups([]);
    onDirty();
  }
  async function scan(file: File | undefined, n: number) {
    if (!file) return;
    setOCRBusy(n);
    setOCRMessage("");
    const form = new FormData();
    form.append("file", file);
    try {
      const result = await api<{
        status: string;
        candidate: Group | null;
        message: string;
      }>(`/inspections/${inspectionId}/items/${item.id}/ocr`, "POST", form);
      setOCRMessage(result.message);
      if (result.status === "CANDIDATE" && result.candidate) {
        changeGroup(n, {
          expiry_state: "KNOWN",
          input_value: result.candidate.input_value,
          source: "OCR",
          confirmed: false,
          month_end_confirmed: false,
          unknown_reason: null,
        });
      }
    } catch (e) {
      onError(e);
    } finally {
      setOCRBusy(null);
    }
  }
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    await onSave({
      actual_qty: Number(qty),
      confirmed,
      groups: groups.map((g) => ({
        qty: g.qty,
        expiry_state: g.expiry_state,
        input_value: g.input_value || "",
        unknown_reason: g.unknown_reason || null,
        confirmed: g.confirmed || false,
        month_end_confirmed: g.month_end_confirmed || false,
        source: g.source || "MANUAL",
      })),
    });
  }
  const needDates = item.requires_expiry && Number(qty) > 0;
  const sum = groups.reduce((s, g) => s + (Number(g.qty) || 0), 0);
  return (
    <form className="item-editor" onSubmit={submit}>
      <div className="item-kicker">
        ПОЗИЦИЯ {index + 1} ИЗ {total}
      </div>
      <h2>{item.name}</h2>
      <p className="muted">
        Единица учёта: {item.unit}. Количество включает все найденные единицы.
      </p>
      <div className="quantity-row">
        <div className="required-qty">
          <small>По шаблону</small>
          <strong>
            {item.required_qty}
            <span>{item.unit}</span>
          </strong>
        </div>
        <label>
          Фактически найдено
          <input
            type="number"
            inputMode="numeric"
            min={0}
            max={9999}
            step={1}
            required
            value={qty}
            placeholder="Введите число"
            onChange={(e) => updateQty(e.target.value)}
          />
        </label>
      </div>
      {needDates && (
        <div className="expiry-section">
          <div className="section-heading">
            <div>
              <h3>Группы сроков годности</h3>
              <p>Разделите предметы по датам на упаковке</p>
            </div>
          </div>
          {groups.map((g, n) => (
            <div className="expiry-group" key={n}>
              <div className="group-header">
                <strong>Группа {n + 1}</strong>
                <button
                  type="button"
                  className="icon-button danger"
                  aria-label={`Удалить группу ${n + 1}`}
                  onClick={() => {
                    setGroups(groups.filter((_, j) => j !== n));
                    onDirty();
                  }}
                >
                  <Trash2 size={15} />
                </button>
              </div>
              <div className="group-fields">
                <label>
                  Количество, {item.unit}
                  <input
                    type="number"
                    min={1}
                    max={9999}
                    step={1}
                    required
                    value={g.qty || ""}
                    onChange={(e) =>
                      changeGroup(n, {
                        qty: Number(e.target.value),
                        confirmed: false,
                      })
                    }
                  />
                </label>
                <label>
                  Срок
                  <select
                    value={g.expiry_state}
                    onChange={(e) =>
                      changeGroup(n, {
                        expiry_state: e.target.value as Group["expiry_state"],
                        input_value: "",
                        confirmed: false,
                        unknown_reason:
                          e.target.value === "UNKNOWN" ? "UNREADABLE" : null,
                      })
                    }
                  >
                    <option value="KNOWN">Дата известна</option>
                    <option value="UNKNOWN">Срок не установлен</option>
                  </select>
                </label>
              </div>
              {g.expiry_state === "KNOWN" ? (
                <>
                  <label>
                    Дата на упаковке
                    <div className="date-input">
                      <input
                        required
                        value={g.input_value || ""}
                        placeholder="ДД.ММ.ГГГГ или ММ/ГГГГ"
                        onChange={(e) =>
                          changeGroup(n, {
                            input_value: e.target.value,
                            source: "MANUAL",
                            confirmed: false,
                            month_end_confirmed: false,
                          })
                        }
                      />
                      <label
                        className={`camera-button ${ocrBusy === n ? "disabled" : ""}`}
                        title="Сфотографировать или загрузить маркировку"
                      >
                        <Camera size={19} />
                        <span>{ocrBusy === n ? "Читаем…" : "Считать"}</span>
                        <input
                          aria-label={`Фото маркировки группы ${n + 1}`}
                          type="file"
                          accept="image/jpeg,image/png"
                          capture="environment"
                          disabled={ocrBusy !== null}
                          onChange={(e) => {
                            scan(e.target.files?.[0], n);
                            e.target.value = "";
                          }}
                        />
                      </label>
                    </div>
                  </label>
                  {/^\d{2}\/\d{4}$/.test(g.input_value || "") && (
                    <label className="checkbox-line month-policy">
                      <input
                        type="checkbox"
                        checked={g.month_end_confirmed || false}
                        onChange={(e) =>
                          changeGroup(n, {
                            month_end_confirmed: e.target.checked,
                          })
                        }
                      />
                      Применить последний день месяца (MONTH_END_V1)
                    </label>
                  )}
                  <label className="checkbox-line">
                    <input
                      type="checkbox"
                      checked={g.confirmed || false}
                      onChange={(e) =>
                        changeGroup(n, { confirmed: e.target.checked })
                      }
                    />
                    Я сверил(а) и подтверждаю дату
                    {g.source === "OCR" ? " после распознавания" : ""}
                  </label>
                </>
              ) : (
                <label>
                  Причина
                  <select
                    value={g.unknown_reason || "UNREADABLE"}
                    onChange={(e) =>
                      changeGroup(n, { unknown_reason: e.target.value })
                    }
                  >
                    <option value="UNREADABLE">Маркировка не читается</option>
                    <option value="NO_MARK">Маркировка отсутствует</option>
                    <option value="AMBIGUOUS">Маркировка неоднозначна</option>
                  </select>
                </label>
              )}
            </div>
          ))}
          <button
            type="button"
            className="secondary full dashed"
            disabled={groups.length >= 20}
            onClick={() => {
              setGroups([
                ...groups,
                {
                  qty: Math.max(Number(qty) - sum, 1),
                  expiry_state: "KNOWN",
                  input_value: "",
                  confirmed: false,
                  source: "MANUAL",
                },
              ]);
              onDirty();
            }}
          >
            <Plus size={16} />
            Добавить группу
          </button>
          <div
            className={`group-total ${sum !== Number(qty) ? "warning-text" : ""}`}
          >
            В группах: {sum} из {qty} {item.unit}
            {sum === Number(qty) ? (
              <Check size={15} />
            ) : (
              <TriangleAlert size={15} />
            )}
          </div>
          {ocrMessage && (
            <div className="alert warning" role="status">
              {ocrMessage}
            </div>
          )}
          <small className="muted">
            Фото обрабатывается локально на сервере. Дату всегда подтверждает
            человек. Можно ввести вручную.
          </small>
        </div>
      )}
      {!needDates && qty !== "" && (
        <div className="alert info">
          <ShieldCheck size={18} />
          {Number(qty) === 0
            ? "При нулевом остатке сроки не требуются. Недостача попадёт в отчёт."
            : "Для этой позиции контроль срока не предусмотрен шаблоном."}
        </div>
      )}
      <label className="checkbox-line confirm-quantity">
        <input
          type="checkbox"
          required
          checked={confirmed}
          onChange={(e) => {
            setConfirmed(e.target.checked);
            onDirty();
          }}
        />
        Я проверил(а) наличие и количество
      </label>
      <button
        className="primary full"
        disabled={
          busy ||
          ocrBusy !== null ||
          qty === "" ||
          !confirmed ||
          (needDates && sum !== Number(qty))
        }
      >
        {busy ? "Сохраняем…" : "Подтвердить и сохранить"}
        <ArrowRight size={17} />
      </button>
    </form>
  );
}
function Result({ inspection: i }: { inspection: Inspection }) {
  const isCancelled = i.lifecycle === "CANCELLED";
  return (
    <>
      <div className="page-heading">
        <div>
          <div className="eyebrow">
            ПРОВЕРКА #{i.id} · {isCancelled ? "ОТМЕНЕНА" : "ЗАВЕРШЕНА"}
          </div>
          <h1>{i.snapshot.kit_name}</h1>
          <p>
            {dateLabel(i.completed_at || i.started_at)} ·{" "}
            {i.snapshot.inspector_name}
          </p>
        </div>
        {!isCancelled && (
          <a
            className="primary"
            href={`/api/v1/inspections/${i.id}/report.pdf`}
          >
            <ArrowDownToLine size={17} />
            Скачать PDF
          </a>
        )}
      </div>
      {isCancelled ? (
        <div className="alert warning">
          Причина отмены: {i.cancellation_reason}
        </div>
      ) : (
        <>
          <div className={`result-banner ${i.result === "OK" ? "good" : ""}`}>
            {i.result === "OK" ? (
              <ShieldCheck size={32} />
            ) : (
              <TriangleAlert size={32} />
            )}
            <div>
              <h2>
                {i.result === "OK"
                  ? "Отклонений по чек-листу не найдено"
                  : "Проверка завершена: есть замечания"}
              </h2>
              <p>
                Результат зафиксирован на {dateLabel(i.inspection_date)} ·{" "}
                {i.snapshot.timezone}. Для исправлений начните новую проверку.
              </p>
            </div>
          </div>
          <div className="stats-grid result-stats">
            {[
              ["shortage_qty", "Недостача"],
              ["expired_qty", "Просрочено"],
              ["unknown_qty", "Срок не установлен"],
              ["replenish_qty", "Пополнить"],
            ].map(([key, label]) => (
              <div className="stat" key={key}>
                <small>{label}, единиц</small>
                <strong>
                  {i.items.reduce(
                    (s, it) => s + Number(it[key as keyof Item] || 0),
                    0,
                  )}
                </strong>
              </div>
            ))}
          </div>
          <div className="result-items">
            {i.items.map((it) => (
              <article className="result-item" key={it.id}>
                <div className="result-item-title">
                  <h3>{it.name}</h3>
                  <span>
                    {it.actual_qty} / {it.required_qty} {it.unit}
                  </span>
                </div>
                <div className="kit-badges">
                  {it.reasons?.length ? (
                    it.reasons.map((r) => (
                      <span className="badge problem" key={r}>
                        {reasons[r]}
                      </span>
                    ))
                  ) : (
                    <Badge value="OK" />
                  )}
                  {!!it.replenish_qty && (
                    <span className="badge neutral">
                      Пополнить: {it.replenish_qty} {it.unit}
                    </span>
                  )}
                </div>
                {it.groups.map((g, n) => (
                  <p className="group-detail" key={n}>
                    {g.qty} {it.unit} ·{" "}
                    {g.expiry_state === "UNKNOWN"
                      ? `Срок не установлен (${({ UNREADABLE: "не читается", NO_MARK: "нет маркировки", AMBIGUOUS: "неоднозначно" } as Record<string, string>)[g.unknown_reason!]})`
                      : `${g.input_value} → ${dateLabel(g.normalized_date!)} · ${g.source === "OCR" ? "OCR, подтверждено" : "ручной ввод"}${g.precision === "MONTH" ? " · последний день месяца" : ""}`}
                  </p>
                ))}
              </article>
            ))}
          </div>
          <div className="bottom-note">
            <FileText size={16} />
            Сохранённый снимок: {i.snapshot.template_name}, версия{" "}
            {i.snapshot.template_version}. Расход после проверки не
            отслеживается.
          </div>
          <p className="muted small">
            Итоги в единицах суммируют разные типы расходников и служат обзором.
            Для пополнения используйте количество и единицы в каждой строке.
            Неизвестный срок можно уточнить новой проверкой.
          </p>
        </>
      )}
    </>
  );
}
function Analytics({
  kits,
  onOpen,
}: {
  kits: Kit[];
  onOpen: (k: Kit) => void;
}) {
  const total = kits.length,
    ok = kits.filter((k) => k.last_result === "OK").length,
    problem = kits.filter((k) => k.last_result === "PROBLEM").length,
    never = total - ok - problem;
  return (
    <div className="analytics-grid">
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Последний результат</h2>
            <p>Каждая аптечка учитывается один раз</p>
          </div>
          <BarChart3 size={22} />
        </div>
        <div className="distribution">
          {[
            [ok, "Без замечаний", "green"],
            [problem, "С замечаниями", "orange"],
            [never, "Не проверены", "gray"],
          ].map(([value, label, color]) => (
            <div key={String(label)}>
              <div>
                <span>
                  <i className={`legend-dot ${color}`} />
                  {label}
                </span>
                <strong>
                  {value} <small>/ {total}</small>
                </strong>
              </div>
              <progress
                className={String(color)}
                value={Number(value)}
                max={total || 1}
              />
            </div>
          ))}
        </div>
        <p className="muted small">
          Это состояние по последним сохранённым проверкам, а не подтверждение
          текущего содержимого.
        </p>
      </section>
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>План обхода</h2>
            <p>Своевременность оценивается отдельно</p>
          </div>
          <CalendarDays size={22} />
        </div>
        {[...kits]
          .sort((a, b) => (a.due_date || "").localeCompare(b.due_date || ""))
          .map((k) => (
            <button
              className="schedule-row"
              key={k.id}
              onClick={() => onOpen(k)}
            >
              <div>
                <strong>{k.name}</strong>
                <small>
                  {k.due_date ? dateLabel(k.due_date) : "Нужна первая проверка"}
                </small>
              </div>
              <Badge value={k.freshness} />
            </button>
          ))}
        {!kits.length && <p className="muted">Добавьте первую аптечку.</p>}
      </section>
      <section className="panel full-panel">
        <div className="section-heading">
          <div>
            <h2>Что показывают эти данные</h2>
            <p>Аналитика для планирования работы</p>
          </div>
          <Activity size={22} />
        </div>
        <div className="insights">
          <div>
            <span>01</span>
            <h3>Приоритет обхода</h3>
            <p>
              {kits.filter((k) => k.freshness !== "CURRENT").length} из {total}{" "}
              аптечек требуют первой или повторной проверки.
            </p>
          </div>
          <div>
            <span>02</span>
            <h3>Работа с замечаниями</h3>
            <p>
              У {problem} аптечек в последнем отчёте есть недостача, просрочка
              или неизвестный срок.
            </p>
          </div>
          <div>
            <span>03</span>
            <h3>Следующий шаг</h3>
            <p>
              Откройте аптечку и историю. Уточните неизвестные даты и проведите
              новую проверку после пополнения.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", escape);
    const el = document.querySelector<HTMLElement>(
      ".modal [data-autofocus], .modal input, .modal button",
    );
    el?.focus();
    const old = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", escape);
      document.body.style.overflow = old;
      previous?.focus();
    };
  }, []);
  function trap(e: React.KeyboardEvent) {
    if (e.key !== "Tab") return;
    const items = Array.from(
      e.currentTarget.querySelectorAll<HTMLElement>(
        "button:not(:disabled),input:not(:disabled),select,textarea,a[href]",
      ),
    );
    const first = items[0],
      last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault();
      last?.focus();
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault();
      first?.focus();
    }
  }
  return (
    <div
      className="modal-overlay"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="modal"
        role="dialog"
        aria-modal="true"
        aria-label={title}
        onKeyDown={trap}
      >
        <div className="modal-title">
          <h2>{title}</h2>
          <button
            className="icon-button"
            aria-label="Закрыть окно"
            onClick={onClose}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}
function KitForm({
  kit,
  templates,
  onClose,
  onSave,
}: {
  kit: Kit | "new";
  templates: Template[];
  onClose: () => void;
  onSave: (body: unknown) => Promise<void>;
}) {
  const initial =
    kit === "new"
      ? {
          name: "",
          location: "",
          template_id: templates[0]?.id || 0,
          interval_days: 30,
        }
      : kit;
  const [body, setBody] = useState({
      name: initial.name,
      location: initial.location,
      template_id: initial.template_id,
      interval_days: initial.interval_days,
    }),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  return (
    <Modal
      title={kit === "new" ? "Новая аптечка" : "Настройки аптечки"}
      onClose={onClose}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await onSave(body);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {error && <div className="alert error">{error}</div>}
        <label>
          Название
          <input
            required
            maxLength={100}
            value={body.name}
            onChange={(e) => setBody({ ...body, name: e.target.value })}
            placeholder="Например, Главный корпус"
          />
        </label>
        <label>
          Локация
          <input
            required
            maxLength={200}
            value={body.location}
            onChange={(e) => setBody({ ...body, location: e.target.value })}
            placeholder="Этаж, помещение, ориентир"
          />
        </label>
        <label>
          Шаблон чек-листа
          <select
            required
            value={body.template_id}
            onChange={(e) =>
              setBody({ ...body, template_id: Number(e.target.value) })
            }
          >
            <option disabled value={0}>
              Сначала создайте шаблон
            </option>
            {templates.map((t) => (
              <option value={t.id} key={t.id}>
                {t.name} · v{t.version}
              </option>
            ))}
          </select>
        </label>
        <label>
          Интервал проверок, дней
          <input
            type="number"
            min={1}
            max={365}
            step={1}
            required
            value={body.interval_days}
            onChange={(e) =>
              setBody({ ...body, interval_days: Number(e.target.value) })
            }
          />
        </label>
        <button className="primary full" disabled={busy || !templates.length}>
          {busy ? "Сохраняем…" : "Сохранить аптечку"}
        </button>
      </form>
    </Modal>
  );
}
function TemplateForm({
  template,
  onClose,
  onSave,
}: {
  template: Template | "new";
  onClose: () => void;
  onSave: (body: unknown) => Promise<void>;
}) {
  const [name, setName] = useState(template === "new" ? "" : template.name),
    [items, setItems] = useState(
      template === "new"
        ? [{ name: "", unit: "шт.", required_qty: 1, requires_expiry: true }]
        : template.items.map(
            ({ name, unit, required_qty, requires_expiry }) => ({
              name,
              unit,
              required_qty,
              requires_expiry,
            }),
          ),
    ),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  function change(n: number, patch: Partial<(typeof items)[0]>) {
    setItems(items.map((i, j) => (j === n ? { ...i, ...patch } : i)));
  }
  return (
    <Modal
      title={
        template === "new"
          ? "Новый шаблон"
          : `Новая версия · v${template.version + 1}`
      }
      onClose={onClose}
    >
      <form
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            await onSave({ name, items });
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {error && <div className="alert error">{error}</div>}
        <label>
          Название шаблона
          <input
            maxLength={100}
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        {template !== "new" && (
          <p className="muted small">
            Изменения создадут новую версию. Начатые и завершённые проверки
            сохранят исходный состав.
          </p>
        )}
        {items.map((i, n) => (
          <div className="template-edit-item" key={n}>
            <div className="group-header">
              <strong>Позиция {n + 1}</strong>
              <button
                type="button"
                className="icon-button danger"
                disabled={items.length === 1}
                aria-label={`Удалить позицию ${n + 1}`}
                onClick={() => setItems(items.filter((_, j) => j !== n))}
              >
                <Trash2 size={16} />
              </button>
            </div>
            <label>
              Наименование
              <input
                maxLength={100}
                required
                value={i.name}
                onChange={(e) => change(n, { name: e.target.value })}
              />
            </label>
            <div className="group-fields">
              <label>
                Норма
                <input
                  type="number"
                  min={0}
                  max={9999}
                  step={1}
                  required
                  value={i.required_qty}
                  onChange={(e) =>
                    change(n, { required_qty: Number(e.target.value) })
                  }
                />
              </label>
              <label>
                Единица
                <input
                  maxLength={30}
                  required
                  value={i.unit}
                  onChange={(e) => change(n, { unit: e.target.value })}
                />
              </label>
            </div>
            <label className="checkbox-line">
              <input
                type="checkbox"
                checked={i.requires_expiry}
                onChange={(e) =>
                  change(n, { requires_expiry: e.target.checked })
                }
              />
              Контроль срока годности
            </label>
          </div>
        ))}
        <button
          type="button"
          className="secondary full dashed"
          disabled={items.length >= 50}
          onClick={() =>
            setItems([
              ...items,
              { name: "", unit: "шт.", required_qty: 1, requires_expiry: true },
            ])
          }
        >
          <Plus size={16} />
          Добавить позицию
        </button>
        <button className="primary full" disabled={busy}>
          {busy ? "Сохраняем…" : "Сохранить версию"}
        </button>
      </form>
    </Modal>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
