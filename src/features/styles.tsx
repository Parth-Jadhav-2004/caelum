import { Button } from "@/components/ui/button";
import type { Config } from "@/lib/ipc";
import { useApp } from "@/stores/app";

const styles = [
  { id: "off", name: "Off", detail: "Keep the transcription without a refinement pass.",
    spoken: "okay let's meet at ten", result: "okay let's meet at ten" },
  { id: "light", name: "Light", detail: "Tidy punctuation and capitalization. Format clearly dictated lists.",
    spoken: "shopping list first rice second oil", result: "Shopping list:\n\n1. Rice\n2. Oil" },
  { id: "thorough", name: "Thorough", detail: "Correct clear grammar mistakes and organize longer dictations.",
    spoken: "the samples was ready we checked them twice", result: "The samples were ready. We checked them twice." },
  { id: "email", name: "Email", detail: "Separate the greeting, message, and sign-off when you dictate them.",
    spoken: "hi Jo the draft is ready thanks Sam", result: "Hi Jo,\n\nThe draft is ready.\n\nThanks,\nSam" },
  { id: "casual", name: "Casual", detail: "Keep contractions and conversational wording.",
    spoken: "hey that's great see you soon", result: "Hey, that's great. See you soon!" },
  { id: "code", name: "Code", detail: "Preserve identifiers, casing, indentation, and technical syntax.",
    spoken: "set retry_count to 3", result: "Set retry_count to 3." },
] as const;

export function Styles({ config, change, saveState }: {
  config: Config; change: (next: Config) => void; saveState: string;
}) {
  const openSettings = useApp((s) => s.openSettings);
  const { cleanup } = config;
  const selected = styles.find((s) => s.id === (cleanup.model ? cleanup.style : "off")) ?? styles[0];
  const groq = cleanup.base_url.replace(/\/+$/, "") === "https://api.groq.com/openai/v1";
  const needsModel = !cleanup.model && !groq;

  return (
    <div className="max-w-3xl space-y-6">
      <h1 tabIndex={-1} className="text-title font-semibold">Styles</h1>
      {config.stt.engine === "local" ? (
        <section className="space-y-3 rounded-lg border bg-card p-5">
          <h2 className="text-section font-medium">You’re dictating on this computer</h2>
          <p className="text-body text-muted-foreground">
            Local dictation formats clear English lists and applies your Dictionary replacements
            automatically. It doesn’t use a refinement model. Writing styles apply to online dictation.
          </p>
          <Button variant="outline" onClick={() => openSettings("Transcription")}>Transcription settings</Button>
        </section>
      ) : (
        <>
          <p className="text-body text-muted-foreground">
            Choose how your online refinement provider edits a transcript before it’s inserted.
            Select Off to skip sending text for refinement.
          </p>
          {needsModel && (
            <div className="flex flex-wrap items-center gap-3 text-body">
              Choose a cleanup model for your provider before enabling a style.
              <Button variant="outline" onClick={() => openSettings("Advanced")}>Provider settings</Button>
            </div>
          )}
          <fieldset>
            <legend className="mb-3 text-section font-medium">Online writing style</legend>
            <div className="grid gap-3 sm:grid-cols-2">
              {styles.map((s) => (
                <label key={s.id} className="flex items-start gap-3 rounded-lg border bg-card p-4 has-checked:border-foreground has-disabled:opacity-60">
                  <input type="radio" className="mt-1 accent-foreground" name="writing-style"
                    aria-label={s.name} aria-describedby={`style-${s.id}`}
                    checked={selected.id === s.id} disabled={s.id !== "off" && needsModel}
                    onChange={() => change({ ...config, cleanup: {
                      ...cleanup,
                      model: s.id === "off" ? "" : cleanup.model || "openai/gpt-oss-20b",
                      style: s.id === "off" ? cleanup.style : s.id,
                      reasoning_effort: groq && s.id !== "off" && (!cleanup.model || cleanup.model === "openai/gpt-oss-20b")
                        ? (s.id === "thorough" ? "high" : "low") : cleanup.reasoning_effort,
                    } })} />
                  <span>
                    <span className="block text-body font-medium">{s.name}</span>
                    <span id={`style-${s.id}`} className="text-meta text-muted-foreground">{s.detail}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
          <section className="space-y-3 rounded-lg border p-5" aria-label="Style example">
            <h2 className="text-section font-medium">{selected.name} example</h2>
            <dl className="grid gap-3 text-body sm:grid-cols-2">
              <div><dt className="text-meta text-muted-foreground">Dictated</dt><dd>{selected.spoken}</dd></div>
              <div><dt className="text-meta text-muted-foreground">Example result</dt><dd className="whitespace-pre-wrap">{selected.result}</dd></div>
            </dl>
          </section>
          <p role="status" className="text-meta text-muted-foreground">{saveState}</p>
        </>
      )}
    </div>
  );
}
