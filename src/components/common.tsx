import { useRef, useState } from "react";
import { Copy, Check, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from "@/components/ui/alert-dialog";
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
} from "@/components/ui/tooltip";
import { errorText } from "@/lib/ipc";
export function briefError(error: unknown) {
  const text = typeof error === "string" ? error : errorText(error);
  if (text.trim().split(/\s+/).length <= 8) return text;
  if (/without encryption|unencrypted/i.test(text))
    return "Key saved without encryption.";
  if (/network|internet|connect|timeout/i.test(text))
    return "Connection lost. Try again.";
  if (/credential|api key|provider key/i.test(text))
    return "Check your API key, then retry.";
  if (/microphone|capture|speech/i.test(text))
    return "Couldn’t hear you. Check your microphone.";
  return "Couldn’t finish. Try again.";
}
export function notifyError(
  error: unknown,
  options: Parameters<typeof toast.error>[1] = {},
) {
  toast.error(briefError(error), {
    action: {
      label: "Details",
      onClick: () => toast.message(errorText(error)),
    },
    ...options,
  });
}
export async function action<T>(run: () => Promise<T>, success?: string) {
  try {
    const result = await run();
    if (success) toast.success(success);
    return result;
  } catch (e) {
    notifyError(e);
    return undefined;
  }
}
export function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          aria-label={copied ? "Copied" : "Copy text"}
          onClick={() => {
            void action(async () => {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setTimeout(() => setCopied(false), 1800);
            });
          }}
        >
          {copied ? <Check /> : <Copy />}
        </Button>
      </TooltipTrigger>
      <TooltipContent>Copy text</TooltipContent>
    </Tooltip>
  );
}
export function Confirm({
  open,
  title,
  detail,
  confirm,
  onCancel,
  onConfirm,
}: {
  open: boolean;
  title: string;
  detail: string;
  confirm: string;
  onCancel: () => void;
  onConfirm: () => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const returnFocus = useRef<HTMLElement | null>(null);
  return (
    <AlertDialog
      open={open}
      onOpenChange={(value) => {
        if (!value && !busy) onCancel();
      }}
    >
      <AlertDialogContent
        onOpenAutoFocus={() => {
          returnFocus.current =
            document.activeElement instanceof HTMLElement
              ? document.activeElement
              : null;
        }}
        onCloseAutoFocus={(event) => {
          const target = returnFocus.current?.isConnected
            ? returnFocus.current
            : document.getElementById("main-content");
          if (target) {
            event.preventDefault();
            target.focus();
          }
        }}
      >
        <AlertDialogHeader>
          <AlertDialogTitle>{title}</AlertDialogTitle>
          <AlertDialogDescription>{detail}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={busy}>Cancel</AlertDialogCancel>
          <AlertDialogAction
            disabled={busy}
            onClick={(event) => {
              event.preventDefault();
              setBusy(true);
              void onConfirm()
                .catch((error) => notifyError(error))
                .finally(() => setBusy(false));
            }}
          >
            {busy && <LoaderCircle className="animate-spin" />}
            {confirm}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
export function Heading({ title }: { title: string }) {
  return (
    <header>
      <h1 tabIndex={-1} className="text-title font-semibold">
        {title}
      </h1>
    </header>
  );
}
