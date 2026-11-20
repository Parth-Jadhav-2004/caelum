import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { RefreshCw } from "lucide-react";
import { version } from "../../package.json";
import { ipc, errorText, type Config } from "@/lib/ipc";
import { action, Confirm } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Row } from "./settings";

export function UpdateSettings({
  config,
  change,
}: {
  config: Config;
  change: (next: Config) => void;
}) {
  const pending = useQuery({
    queryKey: ["updates.pending"],
    queryFn: () => ipc("updates.pending", {}),
  });
  const windows = /Windows/i.test(navigator.userAgent);
  const hasPending = !!pending.data && pending.data.state !== "installed";
  const installAction = windows ? "Open installer" : "Update & restart";
  const [updateChecking, setUpdateChecking] = useState(false),
    [updateStatus, setUpdateStatus] = useState(""),
    [update, setUpdate] = useState<string | null>(null),
    [confirmUpdate, setConfirmUpdate] = useState(false);
  const [testingRelease, setTestingRelease] = useState<{
    version: string;
    installed: boolean;
  } | null>(null);
  async function checkUpdates() {
    setUpdateChecking(true);
    setUpdateStatus("Checking stable and testing releases…");
    setTestingRelease(null);
    try {
      const [stable, preview] = await Promise.allSettled([
        ipc("updates.check", {}),
        ipc("updates.testing", {}),
      ]);
      let message: string;
      if (stable.status === "fulfilled") {
        setUpdate(stable.value?.version ?? null);
        message = stable.value?.version
          ? `Version ${stable.value.version} is available.`
          : "No newer stable release.";
      } else {
        setUpdate(null);
        message = `Could not check stable updates. ${errorText(stable.reason)}`;
      }
      if (preview.status === "fulfilled") {
        setTestingRelease(preview.value || null);
        if (preview.value)
          message += preview.value.installed
            ? ` Testing build ${preview.value.version} is installed.`
            : ` Testing build ${preview.value.version} is available for manual installation.`;
      } else message += " Testing releases could not be checked. Try again.";
      setUpdateStatus(message);
    } finally {
      setUpdateChecking(false);
    }
  }
  return (
    <>
      <Row
        title={`Caelum ${version}`}
        detail={
          hasPending
            ? "An update is queued."
            : update
              ? `Version ${update} available`
              : "Caelum verifies updates against a signed release manifest."
        }
      >
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={updateChecking}
            onClick={() => {
              if (update || hasPending) {
                setConfirmUpdate(true);
                return;
              }
              void checkUpdates();
            }}
          >
            <RefreshCw />
            {update || hasPending ? installAction : "Check updates"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => void action(() => invoke("open_releases"))}
          >
            View releases
          </Button>
          {hasPending && (
            <Button
              variant="ghost"
              onClick={() => {
                void action(
                  () => ipc("updates.discard", {}),
                  "Update removed.",
                ).then(() => pending.refetch());
              }}
            >
              Discard
            </Button>
          )}
        </div>
      </Row>
      {testingRelease && !testingRelease.installed && (
        <Row
          title={`Testing build ${testingRelease.version}`}
          detail="Install this testing release manually with your package manager."
        >
          <Button
            variant="secondary"
            onClick={() =>
              void action(() =>
                invoke("open_releases", {
                  version: testingRelease.version,
                }),
              )
            }
          >
            Download testing build
          </Button>
        </Row>
      )}
      <Row title="Check updates when Caelum opens">
        <Switch
          aria-label="Check updates on launch"
          checked={config.desktop.check_updates}
          onCheckedChange={(v) =>
            change({
              ...config,
              desktop: { ...config.desktop, check_updates: v },
            })
          }
        />
      </Row>
      <p role="status" className="text-meta">
        {updateStatus}
      </p>
      <Confirm
        open={confirmUpdate}
        title={windows ? "Open the Caelum installer?" : `Install ${hasPending ? "queued update" : `Caelum ${update}`}?`}
        detail={windows
          ? "Finish dictation first. Caelum checks the installer against the signed release manifest, then opens it and closes the app. The installer is not Authenticode-signed, so Windows SmartScreen may prompt you. If you cancel, reopen Caelum to retry in Settings."
          : "Caelum verifies the package against the signed release manifest. Administrator authorization is required. Finish dictation first. Settings and history are preserved."}
        confirm={installAction}
        onCancel={() => setConfirmUpdate(false)}
        onConfirm={async () => {
          try {
            const queued = await pending.refetch();
            if (queued.isError) throw queued.error;
            if (!queued.data || queued.data.state === "installed") {
              const available = await ipc("updates.check", {});
              setUpdate(available?.version ?? null);
              if (!available) {
                setUpdateStatus("Caelum is already up to date.");
                setConfirmUpdate(false);
                return;
              }
              await ipc("updates.stage", {});
            }
            const applied = await ipc("updates.apply", {});
            setUpdate(null);
            setConfirmUpdate(false);
            if (applied === "installer_launched") {
              setUpdateStatus("Installer opened. Finish the update in the installer.");
              await invoke("quit_app", { discard: false });
            } else if (applied === "installed") await invoke("restart_app");
            else setUpdateStatus("No update is queued.");
          } catch (error) {
            setUpdateStatus(errorText(error));
            throw error;
          } finally {
            await pending.refetch();
          }
        }}
      />
    </>
  );
}
