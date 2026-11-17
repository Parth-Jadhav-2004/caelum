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
          update
            ? `Version ${update} available`
            : pending.data
              ? "An update is ready to install."
              : "Automatic updates use signed stable releases."
        }
      >
        <div className="flex flex-wrap gap-2">
          <Button
            variant="outline"
            disabled={updateChecking}
            onClick={() => {
              if (update || pending.data) {
                setConfirmUpdate(true);
                return;
              }
              void checkUpdates();
            }}
          >
            <RefreshCw />
            {update || pending.data ? "Update & restart" : "Check updates"}
          </Button>
          <Button
            variant="ghost"
            onClick={() => void action(() => invoke("open_releases"))}
          >
            View releases
          </Button>
          {pending.data && (
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
        title={`Install ${update ? `Caelum ${update}` : "queued update"}?`}
        detail="Downloads and verifies a signed package. Administrator authorization is required. Finish dictation first. Settings and history are preserved."
        confirm="Update & restart"
        onCancel={() => setConfirmUpdate(false)}
        onConfirm={async () => {
          if (!pending.data) await ipc("updates.stage", {});
          await ipc("updates.apply", {});
          await invoke("restart_app");
          setConfirmUpdate(false);
        }}
      />
    </>
  );
}
