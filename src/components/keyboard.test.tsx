import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { Choice } from "@/features/settings";
import { Confirm } from "./common";
import { Button } from "./ui/button";
it("allows keyboard selection and returns focus after closing a theme menu", async () => {
  function View() {
    const [value, setValue] = useState("dark");
    return (
      <Choice
        label="Appearance"
        value={value}
        change={setValue}
        items={[
          ["dark", "Dark"],
          ["light", "Light"],
        ]}
      />
    );
  }
  render(<View />);
  const user = userEvent.setup();
  await user.tab();
  expect(screen.getByRole("combobox")).toHaveFocus();
  await user.keyboard("{ArrowDown}");
  expect(await screen.findByRole("listbox")).toBeInTheDocument();
  await user.keyboard("{End}{Enter}");
  expect(screen.getByRole("combobox")).toHaveTextContent("Light");
  expect(screen.getByRole("combobox")).toHaveFocus();
});
it("puts destructive confirmation on Cancel and returns focus to its opener", async () => {
  const confirm = vi.fn(async () => {});
  function View() {
    const [open, setOpen] = useState(false);
    return (
      <>
        <Button onClick={() => setOpen(true)}>Delete record</Button>
        <Confirm
          open={open}
          title="Delete this record?"
          detail="This deletes the selected record."
          confirm="Delete"
          onCancel={() => setOpen(false)}
          onConfirm={confirm}
        />
      </>
    );
  }
  render(<View />);
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: "Delete record" }));
  expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
  await user.keyboard("{Escape}");
  expect(screen.getByRole("button", { name: "Delete record" })).toHaveFocus();
  expect(confirm).not.toHaveBeenCalled();
});
