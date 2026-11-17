import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import {
  Sidebar,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarProvider,
  SidebarTrigger,
} from "./ui/sidebar";
vi.mock("@/hooks/use-mobile", () => ({ useIsMobile: () => true }));

it("keeps mobile navigation inside a named dialog and closes after navigation", async () => {
  const navigate = vi.fn();
  render(
    <SidebarProvider>
      <Sidebar
        id="main-navigation"
        role="navigation"
        aria-label="Main navigation"
      >
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={navigate}>History</SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </Sidebar>
      <SidebarTrigger />
    </SidebarProvider>,
  );
  const trigger = screen.getByRole("button", { name: "Toggle Sidebar" });
  await userEvent.click(trigger);
  expect(screen.getByRole("dialog", { name: "Sidebar" })).toBeInTheDocument();
  expect(
    screen.getByRole("navigation", { name: "Main navigation" }),
  ).toHaveAttribute("id", "main-navigation");
  await userEvent.click(screen.getByRole("button", { name: "History" }));
  expect(navigate).toHaveBeenCalledOnce();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  expect(trigger).toHaveAttribute("aria-expanded", "false");
});
