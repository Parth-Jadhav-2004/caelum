import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import { useQueryClient } from "@tanstack/react-query";
import { useShallow } from "zustand/react/shallow";
import { ThemeProvider } from "@/lib/theme";
import { MotionConfig } from "motion/react";
import {
  Home,
  Clock3,
  ChartNoAxesColumn,
  Settings as SettingsIcon,
  BookOpen,
  Wand2,
  Pause,
  Play,
} from "lucide-react";
import { useEngine } from "@/hooks/use-engine";
import { useApp, type Page } from "@/stores/app";
import { ipc, errorText, IpcError, type Config, type ConfigPatch } from "@/lib/ipc";
import { formatShortcut } from "@/lib/shortcut";
import { action, Confirm } from "@/components/common";
import {
  SidebarProvider,
  Sidebar,
  SidebarHeader,
  SidebarContent,
  SidebarFooter,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarInset,
  SidebarTrigger,
  useSidebar,
} from "@/components/ui/sidebar";
import {
  CommandDialog,
  CommandInput,
  CommandList,
  CommandEmpty,
  CommandGroup,
  CommandItem,
} from "@/components/ui/command";
import { version } from "../package.json";
import { History } from "@/features/history";
import { CaelumBrand } from "@/components/brand";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { toast } from "sonner";
import { Dashboard, Statistics } from "@/features/dashboard";
const Settings = lazy(() =>
  import("@/features/settings").then((m) => ({ default: m.Settings })),
);
const Dictionary = lazy(() =>
  import("@/features/settings").then((m) => ({ default: m.Dictionary })),
);
const Setup = lazy(() =>
  import("@/features/setup").then((m) => ({ default: m.Setup })),
);
const pages = [
  { id: "home", title: "Home", icon: Home },
  { id: "history", title: "History", icon: Clock3 },
  { id: "dictionary", title: "Dictionary", icon: BookOpen },
  { id: "statistics", title: "Insights", icon: ChartNoAxesColumn },
  { id: "settings", title: "Settings", icon: SettingsIcon },
] as const;
function mergePatch(left: ConfigPatch, right: ConfigPatch): ConfigPatch {
  const result = { ...left };
  for (const section of Object.keys(right) as (keyof Config)[]) {
    Object.assign(result, {
      [section]: { ...left[section], ...right[section] },
    });
  }
  return result;
}
function changedFields(previous: Config | null, next: Config): ConfigPatch {
  if (!previous) return next;
  const patch: ConfigPatch = {};
  for (const section of Object.keys(next) as (keyof Config)[]) {
    const fields = Object.fromEntries(
      Object.entries(next[section]).filter(
        ([key, value]) =>
          JSON.stringify(value) !==
          JSON.stringify(
            (previous[section] as unknown as Record<string, unknown>)[key],
          ),
      ),
    );
    if (Object.keys(fields).length) Object.assign(patch, { [section]: fields });
  }
  return patch;
}
function FrontendReady() {
  useEffect(() => {
    // Mount inside Suspense so the smoke probe cannot pass on a loading shell.
    const timer = window.setTimeout(() => {
      void invoke("frontend_ready").catch(() => {});
    }, 100);
    return () => window.clearTimeout(timer);
  }, []);
  return null;
}
function InvalidSettings({ message, retry }: { message: string; retry: () => void }) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState("");
  const [backup, setBackup] = useState("");
  async function reset() {
    setBusy(true);
    setFailure("");
    try {
      const result = await ipc("settings.reset_invalid", {});
      setBackup(result.backup_path);
    } catch (error) {
      setFailure(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="mx-auto max-w-lg space-y-5 p-8">
      <h1 className="text-xl font-medium">{backup ? "Settings reset" : "Caelum couldn’t read your settings."}</h1>
      {backup ? (
        <>
          <p role="status" className="break-all">Your original settings are backed up at {backup}.</p>
          <Button onClick={() => window.location.reload()}>Continue to setup</Button>
        </>
      ) : (
        <>
          <p className="break-all">{message}</p>
          <p>Edit the file and retry, or back it up and start setup again with default settings.</p>
          {failure && <p role="alert">{failure}</p>}
          <Button disabled={busy} onClick={retry}>Retry connection</Button>{" "}
          <Button disabled={busy} variant="outline" onClick={() => void reset()}>
            Back up and reset settings
          </Button>
        </>
      )}
    </main>
  );
}
function MobileSidebarOpener() {
  const { isMobile } = useSidebar();
  return isMobile ? (
    <header className="flex h-12 shrink-0 items-center px-4 sm:px-8">
      <SidebarTrigger />
    </header>
  ) : null;
}
export default function App() {
  const settingsGroup = useApp((s) => s.settingsGroup);
  const page = useApp((s) => s.page),
    navigate = useApp((s) => s.navigate),
    status = useApp(
      useShallow((s) =>
        s.status
          ? {
              title: s.status.title,
              state: s.status.state,
              running: s.status.running,
              paused: s.status.paused,
              pending_audio: s.status.pending_audio,
              backend: s.status.backend,
              shortcut_mode: s.status.shortcut_mode,
              shortcut_description: s.status.shortcut_description,
            }
          : null,
      ),
    ),
    engineError = useApp((s) => s.engineError);
  const [quitting, setQuitting] = useState(false),
    [restarting, setRestarting] = useState(false),
    [command, setCommand] = useState(false),
    [updateAvailable, setUpdateAvailable] = useState(false),
    [config, setConfig] = useState<Config | null>(null),
    [saveState, setSaveState] = useState("Saved automatically");
  const draft = useRef<Config | null>(null);
  const pendingPatch = useRef<ConfigPatch>({});
  const failedPatch = useRef<ConfigPatch>({});
  const onQuit = useCallback(() => setQuitting(true), []);
  const bootstrap = useEngine(onQuit),
    client = useQueryClient(),
    initialized = useRef(false),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    chain = useRef(Promise.resolve());
  const content = useRef<HTMLDivElement>(null);
  const configured = config !== null;
  useLayoutEffect(() => {
    if (!configured) return;
    content.current?.scrollTo?.({ top: 0, behavior: "instant" });
    // Setup focuses its own step heading once its lazy module has loaded.
    if (page !== "setup")
      content.current
        ?.querySelector<HTMLElement>("h1")
        ?.focus({ preventScroll: true });
  }, [page, configured]);
  useEffect(() => {
    if (!bootstrap.data || initialized.current) return;
    initialized.current = true;
    draft.current = bootstrap.data.config;
    setConfig(bootstrap.data.config);
    // This is a local version check, even when online update checks are off.
    if (/Windows/i.test(navigator.userAgent))
      void ipc("updates.pending", {})
        .then((pending) => {
          if (pending?.state === "installed")
            toast.success(`Update confirmed: Caelum ${pending.version} is running.`);
          else if (pending?.state === "queued") {
            setUpdateAvailable(true);
            toast.info(`Caelum ${pending.version} is not installed yet. Open the installer from Settings to retry.`);
          }
        })
        .catch(() => {});
    if (!bootstrap.data.setup.complete) navigate("setup");
    else {
      void action(() => ipc("service.start", {}));
      if (bootstrap.data.config.desktop.check_updates)
        void ipc("updates.check", {})
          .then((value) => {
            if (value) {
              setUpdateAvailable(true);
              toast.info(`Caelum ${value.version} is available in Settings.`);
            }
          })
          .catch(() => {});
    }
  }, [bootstrap.data, navigate]);
  useEffect(() => {
    const saved = bootstrap.data?.config.stt;
    if (!initialized.current || !saved || !draft.current) return;
    const stt = { ...draft.current.stt };
    for (const key of ["engine", "local_model", "fallback"] as const) {
      if (!Object.hasOwn(pendingPatch.current.stt ?? {}, key) &&
          !Object.hasOwn(failedPatch.current.stt ?? {}, key))
        stt[key] = saved[key];
    }
    if (JSON.stringify(stt) !== JSON.stringify(draft.current.stt)) {
      draft.current = { ...draft.current, stt };
      setConfig(draft.current);
    }
  }, [bootstrap.data]);
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (
        (e.ctrlKey || e.metaKey) &&
        e.key.toLowerCase() === "k" &&
        !e.repeat &&
        !e.defaultPrevented
      ) {
        e.preventDefault();
        setCommand((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  const commit = useCallback(
    async (next: Config) => {
      if (timer.current) clearTimeout(timer.current);
      timer.current = null;
      const patch = mergePatch(
        pendingPatch.current,
        changedFields(draft.current, next),
      );
      pendingPatch.current = {};
      draft.current = next;
      setConfig(next);
      setSaveState("Saving…");
      const operation = chain.current
        .catch(() => {})
        .then(async () => {
          // A preceding queued save may have failed after this edit was submitted.
          const config = mergePatch(failedPatch.current, patch);
          const result = await ipc("settings.save", { config }).catch((error) => {
            failedPatch.current = config;
            throw error;
          });
          failedPatch.current = {};
          setSaveState(result.warning ?? "Saved automatically");
          if (result.warning) toast.warning(result.warning);
          await client.invalidateQueries({ queryKey: ["bootstrap"] });
        });
      chain.current = operation;
      try {
        await operation;
      } catch (error) {
        setSaveState(`Not saved: ${errorText(error)}`);
        throw error;
      }
    },
    [client],
  );
  function change(next: Config) {
    pendingPatch.current = mergePatch(
      pendingPatch.current,
      changedFields(draft.current, next),
    );
    draft.current = next;
    setConfig(next);
    setSaveState("Saving…");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      void action(() => commit(draft.current ?? next));
    }, 200);
  }
  if (bootstrap.isError && bootstrap.error instanceof IpcError && bootstrap.error.code === "invalid_config")
    return <InvalidSettings message={bootstrap.error.message} retry={() => void bootstrap.refetch()} />;
  if (bootstrap.isError)
    return (
      <main className="mx-auto max-w-lg space-y-5 p-8">
        <h1 className="text-xl font-medium">Caelum couldn’t start.</h1>
        <details>
          <summary>Details</summary>
          <p>{errorText(bootstrap.error)}</p>
        </details>
        <Button
          onClick={() => {
            void bootstrap.refetch();
          }}
        >
          Retry connection
        </Button>
        <Button
          variant="outline"
          onClick={() => {
            void action(() => invoke("restart_app"));
          }}
        >
          Restart Caelum
        </Button>
      </main>
    );
  if (!config)
    return (
      <main aria-label="Loading Caelum" aria-busy="true" className="flex h-svh">
        <div
          className="hidden w-60 shrink-0 space-y-6 overflow-hidden border-r bg-sidebar px-4 py-6 md:block [[data-sidebar-collapsed=true]_&]:w-12 [[data-sidebar-collapsed=true]_&]:px-2 [[data-setup-complete=false]_&]:hidden"
          aria-hidden="true"
        >
          <Skeleton className="h-10 w-32" />
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-9" />
          ))}
        </div>
        <div className="min-w-0 flex-1 pt-12 md:pt-0">
          <div className="mx-auto max-w-5xl space-y-8 p-8">
            <Skeleton className="h-10 w-64 max-w-full" />
            <Skeleton className="h-40" />
            <Skeleton className="h-64" />
          </div>
        </div>
      </main>
    );
  return (
    <ThemeProvider
      theme={config.desktop.theme}
      colorTheme={config.desktop.color_theme}
      reducedMotion={config.app.reduced_motion}
      highContrast={config.app.high_contrast}
      sidebarVisible={config.desktop.sidebar_visible}
      setupComplete={bootstrap.data?.setup.complete ?? false}
    >
      <MotionConfig
        reducedMotion={config.app.reduced_motion ? "always" : "user"}
      >
        <TooltipProvider>
          <SidebarProvider
            open={config.desktop.sidebar_visible}
            onOpenChange={(v) =>
              change({
                ...config,
                desktop: { ...config.desktop, sidebar_visible: v },
              })
            }
          >
            <a
              href="#main-content"
              className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded-md focus:bg-background focus:p-3 focus:text-foreground"
            >
              Skip to content
            </a>
            {page !== "setup" && (
              <Sidebar
                id="main-navigation"
                collapsible="icon"
                role="navigation"
                aria-label="Main navigation"
              >
                <SidebarHeader className="h-24 flex-row items-center px-2">
                  <SidebarMenuButton
                    size="lg"
                    aria-label="Caelum home"
                    onClick={() => navigate("home")}
                    className="min-w-0 group-data-[collapsible=icon]:hidden"
                  >
                    <CaelumBrand />
                  </SidebarMenuButton>
                  <SidebarTrigger className="ml-auto shrink-0" />
                </SidebarHeader>
                <SidebarContent className="px-2">
                  {[pages.slice(0, 3), pages.slice(3)].map((group, i) => (
                    <SidebarMenu key={i} className={i ? "mt-6" : ""}>
                      {group.map(({ id, title, icon: Icon }) => (
                        <SidebarMenuItem key={id}>
                          <SidebarMenuButton
                            isActive={page === id}
                            aria-current={page === id ? "page" : undefined}
                            tooltip={title}
                            onClick={() => navigate(id)}
                            className="h-9"
                          >
                            <Icon />
                            <span className="group-data-[collapsible=icon]:sr-only">
                              {title}
                            </span>
                            {page === id && (
                              <span className="ml-auto size-1.5 rounded-full bg-accent-brand group-data-[collapsible=icon]:hidden" />
                            )}
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                      {i === 0 && (
                        <SidebarMenuItem>
                          <SidebarMenuButton
                            disabled
                            aria-label="Styles, coming later"
                            className="h-9"
                          >
                            <Wand2 />
                            <span className="group-data-[collapsible=icon]:sr-only">
                              Styles{" "}
                              <span className="text-meta text-muted-foreground">
                                Coming later
                              </span>
                            </span>
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      )}
                    </SidebarMenu>
                  ))}
                </SidebarContent>
                <SidebarFooter className="gap-4 p-4 group-data-[collapsible=icon]:p-2">
                  <SidebarMenu className="hidden group-data-[collapsible=icon]:flex">
                    <SidebarMenuItem>
                      <SidebarMenuButton
                        tooltip={`${status?.title ?? "Connecting…"} · ${status?.paused ? "Resume" : "Pause"} dictation`}
                        disabled={!status?.running}
                        onClick={() =>
                          void action(() =>
                            ipc("control", {
                              action: status?.paused ? "resume" : "pause",
                            }),
                          )
                        }
                      >
                        {status?.paused ? <Play /> : <Pause />}
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  </SidebarMenu>
                  <div className="space-y-3 rounded-lg border border-sidebar-border bg-sidebar-status p-3 group-data-[collapsible=icon]:hidden">
                    <p
                      role="status"
                      className="flex items-center gap-2 text-body"
                    >
                      <span
                        className={`size-1.5 rounded-full ${status?.state === "error" ? "bg-destructive" : status?.paused || !status?.running || (page === "settings" && settingsGroup === "Appearance") ? "bg-foreground" : "bg-accent-brand"}`}
                      />
                      {status?.title ?? "Connecting…"}
                    </p>
                    {!["home", "settings"].includes(page) &&
                      (status?.backend !== "portable" || status.shortcut_mode === "portal") && (
                        <kbd className="inline-block">
                          {status?.backend === "portable"
                            ? status.shortcut_description
                            : formatShortcut(config.app.hotkey)}
                        </kbd>
                      )}
                    <label className="flex items-center justify-between gap-3 text-body">
                      Pause
                      <Switch
                        aria-label="Pause dictation"
                        disabled={!status?.running}
                        checked={status?.paused ?? false}
                        onCheckedChange={(v) =>
                          void action(() =>
                            ipc("control", { action: v ? "pause" : "resume" }),
                          )
                        }
                      />
                    </label>
                  </div>
                  <div className="flex items-center justify-between text-meta group-data-[collapsible=icon]:hidden">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => void action(() => invoke("open_docs"))}
                    >
                      Help
                    </Button>
                    <span className="flex items-center gap-2 text-muted-foreground">
                      {updateAvailable && (
                        <span
                          className="size-1.5 rounded-full bg-foreground"
                          role="img"
                          aria-label="Update available"
                        />
                      )}
                      {version}
                    </span>
                  </div>
                </SidebarFooter>
              </Sidebar>
            )}
            <SidebarInset>
              {page !== "setup" && <MobileSidebarOpener />}
              <div
                ref={content}
                id="main-content"
                tabIndex={-1}
                aria-label={
                  page === "setup"
                    ? "Setup"
                    : pages.find((p) => p.id === page)?.title
                }
                className={`min-h-0 min-w-0 flex-1 overflow-auto overscroll-contain ${page === "setup" ? "" : "[scrollbar-gutter:stable]"}`}
              >
                {engineError && (
                  <div
                    role="alert"
                    className="mx-8 mt-8 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm"
                  >
                    <div className="min-w-0 space-y-1">
                      <p className="font-medium">Caelum stopped.</p>
                      <p className="break-words text-meta">{engineError}</p>
                    </div>
                    <Button
                      variant="outline"
                      onClick={() => setRestarting(true)}
                    >
                      Restart Caelum
                    </Button>
                  </div>
                )}
                <Suspense fallback={<Skeleton className="m-8 h-80" />}>
                  <div
                    key={page}
                    className={
                      page === "setup"
                        ? "screen-enter h-full"
                        : "screen-enter mx-auto max-w-5xl px-4 py-8 sm:px-8"
                    }
                  >
                    {page === "home" && <Dashboard config={config} />}{" "}
                    {page === "statistics" && <Statistics />}
                    {page === "history" && <History />}
                    {page === "dictionary" && (
                      <div className="space-y-8">
                        <h1 tabIndex={-1} className="text-title font-semibold">
                          Dictionary
                        </h1>
                        <Dictionary config={config} change={change} />
                      </div>
                    )}
                    {page === "settings" && (
                      <Settings
                        initialGroup={settingsGroup}
                        config={config}
                        change={change}
                        saveState={saveState}
                        commit={commit}
                      />
                    )}{" "}
                    {page === "setup" && (
                      <Setup config={config} commit={commit} />
                    )}
                  </div>
                  <FrontendReady />
                </Suspense>
              </div>
            </SidebarInset>
          </SidebarProvider>
          <CommandDialog open={command} onOpenChange={setCommand}>
            <CommandInput placeholder="Go to…" />
            <CommandList>
              <CommandEmpty>No matching page.</CommandEmpty>
              <CommandGroup heading="Navigation">
                {[
                  ...pages,
                  ...(bootstrap.data?.setup.complete && page !== "setup"
                    ? [
                        {
                          id: "setup",
                          title: "Manage keys",
                          icon: SettingsIcon,
                        },
                      ]
                    : []),
                ].map(({ id, title, icon: Icon }) => (
                  <CommandItem
                    key={id}
                    onSelect={() => {
                      navigate(id as Page);
                      setCommand(false);
                    }}
                  >
                    <Icon />
                    {title}
                  </CommandItem>
                ))}
              </CommandGroup>
            </CommandList>
          </CommandDialog>
          <Confirm
            open={quitting}
            title={
              status?.pending_audio ||
              [
                "starting",
                "listening",
                "recording",
                "processing",
                "refining",
              ].includes(status?.state ?? "")
                ? "Quit and discard this recording?"
                : "Quit Caelum?"
            }
            detail="Caelum and its dictation service will stop. Any active or retryable recording is discarded."
            confirm="Quit Caelum"
            onCancel={() => setQuitting(false)}
            onConfirm={async () => {
              if (timer.current) {
                clearTimeout(timer.current);
                await commit(config).catch(() => {});
              }
              await chain.current.catch(() => {});
              await invoke("quit_app", { discard: true });
            }}
          />
          <Confirm
            open={restarting}
            title="Restart Caelum?"
            detail="An active or retryable recording may be discarded, and unsaved settings may be lost. Recording and transcription requests will not be replayed."
            confirm="Restart Caelum"
            onCancel={() => setRestarting(false)}
            onConfirm={async () => {
              if (timer.current) {
                clearTimeout(timer.current);
                await commit(config).catch(() => {});
              }
              await chain.current.catch(() => {});
              await invoke("restart_app", { discard: true });
            }}
          />
          <Toaster closeButton />
        </TooltipProvider>
      </MotionConfig>
    </ThemeProvider>
  );
}
