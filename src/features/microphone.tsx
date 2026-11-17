import { useEffect, useRef, useState } from "react";
import { listen } from "@tauri-apps/api/event";
import { useQuery } from "@tanstack/react-query";
import { ipc, type Config } from "@/lib/ipc";
import { action, briefError } from "@/components/common";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from "@/components/ui/dialog";

export function useMicrophoneLevel(active: boolean) {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    setLevel(0);
    if (!active) return;
    let disposed = false;
    let stop: (() => void) | undefined;
    void listen<{ level: number }>("engine:microphone", (event) => {
      if (!disposed) setLevel(event.payload.level);
    })
      .then((fn) => {
        if (disposed) fn();
        else stop = fn;
      })
      .catch(() => {});
    return () => {
      disposed = true;
      stop?.();
    };
  }, [active]);
  return active ? level : 0;
}
export function MicrophoneMeter({ level }: { level: number }) {
  const percent = Math.round(Math.max(0, Math.min(1, level)) * 100);
  return (
    <div
      role="meter"
      aria-label="Microphone level"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={percent}
      aria-valuetext={`${percent} percent`}
      className="h-3 w-full overflow-hidden rounded-full bg-muted"
    >
      <div
        className="h-full rounded-full bg-foreground transition-[width] duration-100"
        style={{ width: `${percent}%` }}
      />
    </div>
  );
}
function MicrophoneCheck({
  device,
  onClose,
}: {
  device: Config["app"]["microphone"];
  onClose: () => void;
}) {
  const [listening, setListening] = useState(true);
  const [message, setMessage] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [stopping, setStopping] = useState(false);
  const [capturePending, setCapturePending] = useState(true);
  const stopped = useRef(false);
  const level = useMicrophoneLevel(listening);
  const devices = useQuery({
    queryKey: ["devices"],
    queryFn: () => ipc("devices", {}),
  });
  const name =
    device === null
      ? "System microphone"
      : (devices.data?.find((d) => d.value === device)?.label ??
        String(device));
  useEffect(() => {
    let disposed = false;
    let finished = false;
    stopped.current = false;
    setListening(true);
    setCapturePending(true);
    setMessage("");
    void ipc("microphone.test", {})
      .then(() => {
        if (!disposed && !stopped.current) setMessage("We hear you ✓");
      })
      .catch((error) => {
        if (!disposed && !stopped.current) setMessage(briefError(error));
      })
      .finally(() => {
        finished = true;
        if (!disposed) {
          setListening(false);
          setCapturePending(false);
        }
      });
    return () => {
      disposed = true;
      if (!finished) void ipc("sample.cancel", {}).catch(() => {});
    };
  }, [attempt]);
  return (
    <>
      <p className="text-body font-medium">{name}</p>
      <MicrophoneMeter level={level} />
      <p role="status" className="min-h-5 text-meta text-muted-foreground">
        {message || (listening ? "Listening…" : "Stopped")}
      </p>
      <div className="flex justify-end gap-2">
        {listening && (
          <Button
            variant="ghost"
            onClick={() => {
              stopped.current = true;
              setListening(false);
              setStopping(true);
              void action(() => ipc("sample.cancel", {})).finally(() =>
                setStopping(false),
              );
            }}
          >
            Stop
          </Button>
        )}
        {!listening && (
          <Button
            variant="ghost"
            disabled={stopping || capturePending}
            onClick={() => setAttempt((value) => value + 1)}
          >
            Test again
          </Button>
        )}
        <Button variant="secondary" onClick={onClose}>
          Close
        </Button>
      </div>
    </>
  );
}
export function MicrophoneTestDialog({
  open,
  onOpenChange,
  device,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  device: Config["app"]["microphone"];
}) {
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        showCloseButton={false}
        className="sm:max-w-sm"
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement
              ? document.activeElement
              : null;
        }}
        onCloseAutoFocus={(event) => {
          if (returnFocus.current?.isConnected) {
            event.preventDefault();
            returnFocus.current.focus();
          }
        }}
      >
        <DialogHeader>
          <DialogTitle>Test your microphone</DialogTitle>
          <DialogDescription>Say a few words.</DialogDescription>
        </DialogHeader>
        {open && (
          <MicrophoneCheck
            device={device}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}
