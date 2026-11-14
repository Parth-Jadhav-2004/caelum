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
  AudioLines,
  Home,
  Clock3,
  ChartNoAxesColumn,
  Settings as SettingsIcon,
  Command as CommandIcon,
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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Toaster } from "@/components/ui/sonner";
import { TooltipProvider } from "@/components/ui/tooltip";
import { toast } from "sonner";
import { Dashboard, Statistics } from "@/features/dashboard";
const History = lazy(() =>
  import("@/features/history").then((m) => ({ default: m.History })),
);
const Settings = lazy(() =>
  import("@/features/settings").then((m) => ({ default: m.Settings })),
);
const Setup = lazy(() =>
  import("@/features/setup").then((m) => ({ default: m.Setup })),
);
const pages = [
  { id: "home", title: "Home", icon: Home },
  { id: "statistics", title: "Statistics", icon: ChartNoAxesColumn },
  { id: "history", title: "History", icon: Clock3 },
  { id: "settings", title: "Settings", icon: SettingsIcon },
] as const;
export default function App() {
  const page = useApp((s) => s.page),
    navigate = useApp((s) => s.navigate),
    status = useApp((s) => s.status);
  const [quitting, setQuitting] = useState(false),
    [command, setCommand] = useState(false),
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
            if (value)
              toast.info(`Caelum ${value.version} is available in Settings.`);
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
      void action(() => commit(next));
    }, 450);
  }
  if (bootstrap.isError)
    return (
      <main className="mx-auto max-w-lg space-y-5 p-10">
        <h1 className="text-xl font-medium">
          Caelum couldn’t connect to its engine.
        </h1>
        <p>{errorText(bootstrap.error)}</p>
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
      <main className="space-y-6 p-10">
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
            <Sidebar collapsible="icon">
              <SidebarHeader className="px-4 py-7">
                <SidebarMenu>
                  <SidebarMenuItem>
                    <SidebarMenuButton
                      size="lg"
                      onClick={() => navigate("home")}
                    >
                      <AudioLines className="size-7! text-primary" />
                      <div>
                        <p className="text-lg font-semibold tracking-tight">
                          Caelum
                        </p>
                        <p className="text-xs text-muted-foreground">
                          Voice dictation
                        </p>
                      </div>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                </SidebarMenu>
              </SidebarHeader>
              <SidebarContent className="px-2">
                <SidebarMenu>
                  {pages.map(({ id, title, icon: Icon }) => (
                    <SidebarMenuItem key={id}>
                      <SidebarMenuButton
                        isActive={
                          page === id || (id === "settings" && page === "setup")
                        }
                        tooltip={title}
                        onClick={() => navigate(id)}
                        className="h-11"
                      >
                        <Icon />
                        <span>{title}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  ))}
                </SidebarMenu>
              </SidebarContent>
              <SidebarFooter className="gap-4 border-t p-4">
                <p className="flex items-center gap-2 text-xs text-muted-foreground group-data-[collapsible=icon]:hidden">
                  <span className="size-1.5 rounded-full bg-primary" />
                  {status?.title ?? "Connecting…"}
                </p>
                <div className="space-y-2 group-data-[collapsible=icon]:hidden">
                  <p className="text-xs text-muted-foreground">
                    {config.app.recording_mode === "hold"
                      ? "Hold to talk"
                      : "Press to toggle"}
                  </p>
                  <p className="font-mono text-xs">{config.app.hotkey}</p>
                </div>
              </SidebarFooter>
            </Sidebar>
            <SidebarInset>
              <header className="flex h-16 shrink-0 items-center justify-between border-b px-5">
                <div className="flex items-center gap-3">
                  <SidebarTrigger />
                  <span className="text-xs text-muted-foreground">
                    {pages.find((p) => p.id === page)?.title ?? "Setup"}
                  </span>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-muted-foreground"
                  aria-label="Open command menu"
                  onClick={() => setCommand(true)}
                >
                  <CommandIcon className="size-3.5" />
                  <span className="hidden sm:inline">Quick navigation</span>
                  <kbd className="text-xs">Ctrl K</kbd>
                </Button>
              </header>
              <main className="min-w-0 flex-1 overflow-auto">
                <Suspense fallback={<Skeleton className="m-8 h-80" />}>
                  <motion.div
                    key={page}
                    initial={{ opacity: 0.5, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.16 }}
                    className="mx-auto max-w-5xl px-5 py-8 sm:px-10 sm:py-10"
                  >
                    {page === "home" && (
                      <Dashboard
                        config={config}
                        onMicrophone={(value) =>
                          change({
                            ...config,
                            app: { ...config.app, microphone: value },
                          })
                        }
                      />
                    )}{" "}
                    {page === "statistics" && <Statistics />}
                    {page === "history" && <History />}
                    {page === "settings" && (
                      <Settings
                        config={config}
                        change={change}
                        saveState={saveState}
                      />
                    )}{" "}
                    {page === "setup" && (
                      <Setup config={config} commit={commit} />
                    )}
                  </motion.div>
                </Suspense>
              </main>
            </SidebarInset>
          </SidebarProvider>
          <CommandDialog open={command} onOpenChange={setCommand}>
            <CommandInput placeholder="Go to…" />
            <CommandList>
              <CommandEmpty>No matching page.</CommandEmpty>
              <CommandGroup heading="Navigation">
                {[
                  ...pages,
                  { id: "setup", title: "Setup & keys", icon: SettingsIcon },
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
          <Toaster richColors closeButton />
        </TooltipProvider>
      </MotionConfig>
    </ThemeProvider>
  );
}
