import { useState } from "react";
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
export async function action<T>(run: () => Promise<T>, success?: string) {
  try {
    const result = await run();
    if (success) toast.success(success);
    return result;
  } catch (e) {
    toast.error(errorText(e));
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
            }, "Copied. Clipboard managers may retain this text.");
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
  return (
    <AlertDialog
      open={open}
      onOpenChange={(value) => {
        if (!value && !busy) onCancel();
      }}
    >
      <AlertDialogContent>
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
                .catch((error) => toast.error(errorText(error)))
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
export function Heading({
  eyebrow,
  title,
  detail,
}: {
  eyebrow?: string;
  title: string;
  detail: string;
}) {
  return (
    <header className="space-y-2">
      {eyebrow && (
        <p className="text-xs font-medium tracking-[.16em] text-primary uppercase">
          {eyebrow}
        </p>
      )}
      <h1 className="text-3xl font-semibold tracking-tight">{title}</h1>
      <p className="text-sm leading-6 text-muted-foreground">{detail}</p>
    </header>
  );
}
