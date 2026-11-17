import {
  Suspense,
  lazy,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import { invoke } from "@tauri-apps/api/core";
import { useQueryClient } from "@tanstack/react-query";
import { ThemeProvider } from "@/lib/theme";
import { MotionConfig, motion } from "motion/react";
import {
  Home,
  Clock3,
  ChartNoAxesColumn,
  Settings as SettingsIcon,
  BookOpen,
  Wand2,
  Info,
} from "lucide-react";
import { useEngine } from "@/hooks/use-engine";
import { useApp, type Page } from "@/stores/app";
import { ipc, errorText, type Config } from "@/lib/ipc";
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
import { Settings, Choice, Dictionary } from "@/features/settings";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import {
  TooltipProvider,
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { toast } from "sonner";
import { Dashboard, Statistics } from "@/features/dashboard";
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
export default function App() {
  const settingsGroup = useApp((s) => s.settingsGroup);
  const page = useApp((s) => s.page),
    navigate = useApp((s) => s.navigate),
    status = useApp((s) => s.status),
    engineError = useApp((s) => s.engineError);
  const [quitting, setQuitting] = useState(false),
    [restarting, setRestarting] = useState(false),
    [command, setCommand] = useState(false),
    [updateAvailable, setUpdateAvailable] = useState(false),
    [config, setConfig] = useState<Config | null>(null),
    [saveState, setSaveState] = useState("Saved automatically");
  const onQuit = useCallback(() => setQuitting(true), []);
  const bootstrap = useEngine(onQuit),
    client = useQueryClient(),
    initialized = useRef(false),
    timer = useRef<ReturnType<typeof setTimeout> | null>(null),
    chain = useRef(Promise.resolve());
  useEffect(() => {
    if (!bootstrap.data || initialized.current) return;
    initialized.current = true;
    setConfig(bootstrap.data.config);
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
    const handler = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") {
        e.preventDefault();
        setCommand((v) => !v);
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);
  useEffect(() => {
    document.documentElement.dataset.reducedMotion = String(
      config?.app.reduced_motion ?? false,
    );
    document.documentElement.dataset.highContrast = String(
      config?.app.high_contrast ?? false,
    );
  }, [config?.app.reduced_motion, config?.app.high_contrast]);
  const commit = useCallback(
    async (next: Config) => {
      if (timer.current) clearTimeout(timer.current);
      setConfig(next);
      setSaveState("Saving…");
      const operation = chain.current
        .catch(() => {})
        .then(async () => {
          const result = await ipc("settings.save", { config: next });
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
    setConfig(next);
    setSaveState("Saving…");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      timer.current = null;
      void action(() => commit(next));
    }, 200);
  }
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
      <main className="space-y-6 p-8">
        <Skeleton className="h-10 w-56" />
        <Skeleton className="h-80 w-full" />
      </main>
    );
  return (
    <ThemeProvider
      theme={config.desktop.theme}
      colorTheme={config.desktop.color_theme}
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
                collapsible="icon"
                role="navigation"
                aria-label="Main navigation"
              >
                <SidebarHeader className="px-4 py-6">
                  <SidebarMenu>
                    <SidebarMenuItem>
                      <SidebarMenuButton
                        size="lg"
                        aria-label="Caelum home"
                        onClick={() => navigate("home")}
                      >
                        <CaelumBrand />
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  </SidebarMenu>
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
                            <span>{title}</span>
                            {page === id && (
                              <span className="ml-auto size-1.5 rounded-full bg-accent-brand group-data-[collapsible=icon]:hidden" />
                            )}
                          </SidebarMenuButton>
                        </SidebarMenuItem>
                      ))}
                      {i === 0 && (
                        <SidebarMenuItem>
                          <SidebarMenuButton disabled className="h-9">
                            <Wand2 />
                            <span>
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
                <SidebarFooter className="gap-4 p-4">
                  <div className="space-y-3 rounded-lg bg-sidebar-status p-3 group-data-[collapsible=icon]:hidden">
                    <p
                      role="status"
                      className="flex items-center gap-2 text-body"
                    >
                      <span
                        className={`size-1.5 rounded-full ${status?.state === "error" ? "bg-destructive" : status?.paused || !status?.running || (page === "settings" && settingsGroup === "Appearance") ? "bg-foreground" : "bg-accent-brand"}`}
                      />
                      {status?.title ?? "Connecting…"}
                    </p>
                    {!["home", "settings"].includes(page) && (
                      <kbd className="inline-block">{config.app.hotkey}</kbd>
                    )}
                    {page !== "settings" && (
                      <>
                        <Choice
                          label="Recording mode"
                          value={config.app.recording_mode}
                          items={[
                            ["hold", "Hold"],
                            ["toggle", "Toggle"],
                          ]}
                          change={(v) =>
                            change({
                              ...config,
                              app: { ...config.app, recording_mode: v },
                            })
                          }
                        />
                      </>
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
              {page !== "setup" && (
                <header className="flex h-12 shrink-0 items-center px-8">
                  <SidebarTrigger />
                </header>
              )}
              <div
                id="main-content"
                tabIndex={-1}
                className="min-w-0 flex-1 overflow-auto"
              >
                {engineError && (
                  <div
                    role="alert"
                    className="mx-8 mt-8 flex flex-wrap items-center justify-between gap-4 rounded-lg border border-destructive/30 bg-destructive/10 p-4 text-sm"
                  >
                    <Tooltip>
                      <TooltipTrigger asChild>
                        <button
                          className="flex items-center gap-2 font-medium"
                          aria-label="Why Caelum stopped"
                        >
                          Caelum stopped.
                          <Info className="size-4" />
                        </button>
                      </TooltipTrigger>
                      <TooltipContent className="max-w-sm">
                        {engineError}
                      </TooltipContent>
                    </Tooltip>
                    <Button
                      variant="outline"
                      onClick={() => setRestarting(true)}
                    >
                      Restart Caelum
                    </Button>
                  </div>
                )}
                <Suspense fallback={<Skeleton className="m-8 h-80" />}>
                  <motion.div
                    key={page}
                    initial={{ opacity: 0.5, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.16 }}
                    className="mx-auto max-w-5xl px-8 py-8"
                  >
                    {page === "home" && <Dashboard config={config} />}{" "}
                    {page === "statistics" && <Statistics />}
                    {page === "history" && <History />}
                    {page === "dictionary" && (
                      <div className="space-y-8">
                        <h1 className="text-title font-semibold">Dictionary</h1>
                        <Dictionary config={config} change={change} />
                      </div>
                    )}
                    {page === "settings" && (
                      <Settings
                        initialGroup={settingsGroup}
                        config={config}
                        change={change}
                        saveState={saveState}
                      />
                    )}{" "}
                    {page === "setup" && (
                      <Setup config={config} commit={commit} />
                    )}
                  </motion.div>
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
