import { useEffect, useState } from "react";
import { invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, ArrowRight, Eye, EyeOff, KeyRound } from "lucide-react";
import { ipc, type Config, errorText } from "@/lib/ipc";
import { useApp } from "@/stores/app";
import { action, CopyButton, Heading, Confirm } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { Card, CardContent } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Choice, Shortcut } from "./settings";
import { DeviceSelect, Waveform } from "./dashboard";
const steps = ["Provider", "Microphone", "Shortcut", "Practice"];
export function Setup({
  config,
  commit,
}: {
  config: Config;
  commit: (next: Config) => Promise<void>;
}) {
  const navigate = useApp((s) => s.navigate);
  const [step, setStep] = useState(0),
    [key, setKey] = useState(""),
    [pendingKeys, setPendingKeys] = useState<Record<string, string>>({}),
    [name, setName] = useState(config.stt.key_env),
    [revealed, reveal] = useState(false),
    [consent, setConsent] = useState(false),
    [training, setTraining] = useState(false),
    [upload, setUpload] = useState(false),
    [busy, setBusy] = useState(false),
    [notice, setNotice] = useState(""),
    [micPassed, setMicPassed] = useState(false),
    [practice, setPractice] = useState(""),
    [level, setLevel] = useState(0),
    [remove, setRemove] = useState(false);
  const bootstrap = useQuery({
    queryKey: ["bootstrap"],
    queryFn: () => ipc("bootstrap", {}),
  });
  useEffect(() => {
    let stop: (() => void) | undefined;
    let disposed = false;
    void listen<{ level: number }>("engine:microphone", (e) =>
      setLevel(e.payload.level),
    ).then((fn) => {
      if (disposed) fn();
      else stop = fn;
    });
    return () => {
      disposed = true;
      stop?.();
      void ipc("sample.cancel", {});
    };
  }, []);
  async function advance() {
    setBusy(true);
    setNotice("");
    try {
      if (step === 0) {
        if (!consent)
          throw new Error("Consent to provider processing is required.");
        if (
          (config.cleanup.model + " " + config.cleanup.base_url)
            .toLowerCase()
            .includes("contributor")
        ) {
          if (!training)
            throw new Error(
              "This Contributor model uses text for training. Explicit consent is required.",
            );
          await commit({
            ...config,
            cleanup: {
              ...config.cleanup,
              contributor_consent:
                config.cleanup.base_url.replace(/\/$/, "") +
                "|" +
                config.cleanup.model,
            },
          });
        }
        const keys = { ...pendingKeys, ...(key ? { [name]: key } : {}) };
        setPendingKeys(keys);
        const result = await ipc("setup.validate", { consent, keys });
        setKey("");
        setPendingKeys({});
        if (Object.values(result.storage).includes("file"))
          setNotice(
            "Keyring unavailable. Key saved in an owner-only file, without encryption.",
          );
        await bootstrap.refetch();
        setStep(1);
      } else if (step === 1) {
        if (!micPassed) {
          await ipc("microphone.test", {});
          setMicPassed(true);
          setNotice("Heard you clearly. Nothing is saved or uploaded.");
        } else setStep(2);
      } else if (step === 2) {
        setNotice(await ipc("shortcut.check", {}));
        setStep(3);
      } else if (!practice) {
        const result = await ipc("practice", { consent: upload });
        setPractice(result.text);
        setNotice(
          result.refined
            ? "Practice complete. Text stays here unless you copy it."
            : "Practice complete · unrefined.",
        );
      } else {
        await ipc("setup.finish", {});
        await bootstrap.refetch();
        navigate("home");
      }
    } catch (error) {
      setNotice(errorText(error));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="mx-auto max-w-2xl space-y-7">
      <Heading
        eyebrow={`Step ${step + 1} of 4 · ${steps[step]}`}
        title={
          [
            "Set up your provider",
            "Test your microphone",
            "Set your recording shortcut",
            "Try dictation",
          ][step]
        }
        detail="Connect your provider, check your microphone, and try dictation."
      />
      <div className="grid grid-cols-4 gap-2">
        {steps.map((title, i) => (
          <div key={title} className="space-y-2">
            <div
              className={`h-1 rounded-full ${i <= step ? "bg-primary" : "bg-muted"}`}
            />
            <p className="text-xs text-muted-foreground">{title}</p>
          </div>
        ))}
      </div>
      <Card className="shadow-none">
        <CardContent className="space-y-6 pt-6">
          {step === 0 && (
            <>
              <KeyRound className="size-8 text-primary" />
              <div className="space-y-2">
                <Label>Credential to edit</Label>
                <Choice
                  label="Credential to edit"
                  value={name}
                  change={setName}
                  items={[
                    ...new Set([
                      config.stt.key_env,
                      ...(config.cleanup.model ? [config.cleanup.key_env] : []),
                    ]),
                  ].map((v) => [v, v])}
                />
                <p className="text-xs text-muted-foreground">
                  {bootstrap.data?.credentials[name]}. Saved keys are never
                  shown.
                </p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="provider-key">Provider API key</Label>
                <div className="flex gap-2">
                  <Input
                    id="provider-key"
                    type={revealed ? "text" : "password"}
                    autoComplete="off"
                    value={key}
                    onChange={(e) => setKey(e.target.value)}
                    disabled={busy}
                    placeholder="Enter a key, or use your saved key"
                  />
                  <Button
                    variant="outline"
                    size="icon"
                    aria-label={revealed ? "Hide key" : "Reveal key"}
                    onClick={() => reveal(!revealed)}
                  >
                    {revealed ? <EyeOff /> : <Eye />}
                  </Button>
                </div>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setRemove(true)}>
                Remove saved key
              </Button>
              <details className="text-xs leading-6 text-muted-foreground">
                <summary className="cursor-pointer font-medium">
                  How Caelum handles your data
                </summary>
                <p>{bootstrap.data?.privacy}</p>
              </details>
              <label className="flex items-start gap-3 text-sm leading-6">
                <Checkbox
                  checked={consent}
                  onCheckedChange={(v) => setConsent(v === true)}
                  className="mt-1"
                />
                I allow audio and optional cleanup text to be sent to the
                selected providers.
              </label>
              {config.stt.base_url.startsWith("https://api.groq.com/") && (
                <Button
                  variant="link"
                  onClick={() => {
                    void action(() => invoke("open_key_console"));
                  }}
                >
                  Get a free Groq key ↗
                </Button>
              )}
              {(config.cleanup.model + " " + config.cleanup.base_url)
                .toLowerCase()
                .includes("contributor") && (
                <label className="flex items-start gap-3 text-sm">
                  <Checkbox
                    checked={training}
                    onCheckedChange={(v) => setTraining(v === true)}
                  />
                  I consent to this Contributor endpoint and model using my text
                  for training.
                </label>
              )}
              <Button variant="link" onClick={() => navigate("settings")}>
                Custom provider settings
              </Button>
            </>
          )}
          {step === 1 && (
            <>
              <DeviceSelect
                value={config.app.microphone}
                disabled={busy}
                onChange={(value) => {
                  setMicPassed(false);
                  void action(() =>
                    commit({
                      ...config,
                      app: { ...config.app, microphone: value },
                    }),
                  );
                }}
              />
              <Waveform values={Array<number>(17).fill(level)} />
              <Progress value={level * 100} aria-label="Microphone level" />
              <p className="text-sm text-muted-foreground">
                Speak during the three-second test. The sample stays on this
                device and is discarded.
              </p>
              {micPassed && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => {
                    setMicPassed(false);
                    void action(
                      () => ipc("microphone.test", {}),
                      "Microphone tested locally.",
                    ).then((result) => {
                      if (result) setMicPassed(true);
                    });
                  }}
                >
                  Test again
                </Button>
              )}
            </>
          )}
          {step === 2 && (
            <>
              <Shortcut
                value={config.app.hotkey}
                change={(value) => {
                  void action(() =>
                    commit({
                      ...config,
                      app: { ...config.app, hotkey: value },
                    }),
                  );
                }}
              />
              <p className="text-sm leading-6 text-muted-foreground">
                Hold to dictate; release to process. Toggle mode uses a second
                press. On portable desktops, your desktop may request shortcut
                permission. Record remains available.
              </p>
            </>
          )}
          {step === 3 && (
            <>
              <label className="flex gap-3 text-sm leading-6">
                <Checkbox
                  checked={upload}
                  disabled={busy}
                  onCheckedChange={(v) => setUpload(v === true)}
                  className="mt-1"
                />
                I consent to uploading a five-second practice recording to my
                configured providers.
              </label>
              <Waveform values={Array<number>(17).fill(level)} />
              {practice ? (
                <div className="rounded-xl border p-4">
                  <div className="flex justify-between">
                    <p className="text-xs text-muted-foreground">
                      Practice result · never inserted automatically
                    </p>
                    <CopyButton text={practice} />
                  </div>
                  <p className="whitespace-pre-wrap text-sm leading-7">
                    {practice}
                  </p>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">
                  Try: “A little less typing, a little more room to think.”
                </p>
              )}
            </>
          )}
          {notice && (
            <p
              role="status"
              className="whitespace-pre-wrap rounded-lg bg-muted p-4 text-sm leading-6"
            >
              {notice}
            </p>
          )}
        </CardContent>
      </Card>
      <div className="flex flex-wrap justify-between gap-3">
        <Button
          variant="ghost"
          disabled={busy}
          onClick={() => {
            setKey("");
            setPractice("");
            navigate("home");
          }}
        >
          Resume later
        </Button>
        <div className="flex gap-2">
          {busy ? (
            <Button
              variant="outline"
              onClick={() => {
                void action(() => ipc("sample.cancel", {}));
              }}
            >
              Cancel test
            </Button>
          ) : (
            <Button
              variant="outline"
              disabled={step === 0}
              onClick={() => setStep(step - 1)}
            >
              <ArrowLeft />
              Back
            </Button>
          )}
          <Button
            disabled={
              busy || (step === 0 && !consent) || (step === 3 && !upload)
            }
            onClick={() => {
              void advance();
            }}
          >
            {busy
              ? "Working…"
              : step === 1 && !micPassed
                ? "Test microphone"
                : step === 3
                  ? practice
                    ? "Finish"
                    : "Record practice"
                  : "Continue"}
            <ArrowRight />
          </Button>
        </div>
      </div>
      <Confirm
        open={remove}
        title="Remove the saved provider key?"
        detail="Dictation with this key will stop working. Environment fallback is disabled until you save a replacement."
        confirm="Remove key"
        onCancel={() => setRemove(false)}
        onConfirm={async () => {
          await ipc("credentials.delete", { name });
          setRemove(false);
          await bootstrap.refetch();
        }}
      />
    </div>
  );
}
