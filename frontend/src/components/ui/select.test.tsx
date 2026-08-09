import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { useState } from "react"
import { describe, expect, it, vi } from "vitest"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

const roles = [
  { value: "administrator", label: "Quản trị viên" },
  { value: "helpdesk", label: "Điều phối" },
  { value: "technician", label: "Kỹ thuật viên" },
  { value: "property_manager", label: "Quản lý cơ sở" },
]

function RoleSelect({ onValueChange }: { onValueChange: (value: string) => void }) {
  const [value, setValue] = useState("technician")

  return (
    <div data-testid="clipping-card" className="overflow-hidden">
      <label htmlFor="role-select">Vai trò</label>
      <Select
        value={value}
        onValueChange={(nextValue) => {
          setValue(nextValue)
          onValueChange(nextValue)
        }}
      >
        <SelectTrigger id="role-select">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {roles.map((role) => (
            <SelectItem key={role.value} value={role.value}>
              {role.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

function optionLabels() {
  return screen.getAllByRole("option").map((option) => option.textContent)
}

describe("SelectContent", () => {
  it("keeps business order on reopen, marks the selected item, and renders in a popper portal", async () => {
    const onValueChange = vi.fn()
    render(<RoleSelect onValueChange={onValueChange} />)

    const trigger = screen.getByRole("combobox", { name: "Vai trò" })
    fireEvent.click(trigger)

    expect(optionLabels()).toEqual(roles.map((role) => role.label))
    const selected = screen.getByRole("option", { name: "Kỹ thuật viên" })
    expect(selected).toHaveAttribute("data-state", "checked")
    expect(selected.querySelector("svg")).toBeVisible()
    fireEvent.focus(selected)
    expect(selected).toHaveAttribute("data-highlighted")
    expect(selected).toHaveAttribute("aria-selected", "true")

    const content = document.querySelector<HTMLElement>("[data-slot='select-content']")
    expect(content).not.toBeNull()
    expect(content).toHaveAttribute("data-side", "bottom")
    expect(content).toHaveAttribute("data-align", "start")
    expect(content?.querySelector("[data-position='popper']")).not.toBeNull()
    expect(screen.getByTestId("clipping-card")).not.toContainElement(content)

    fireEvent.keyDown(document.activeElement ?? trigger, { key: "Escape" })
    await waitFor(() => expect(screen.queryAllByRole("option")).toHaveLength(0))

    fireEvent.click(trigger)
    expect(optionLabels()).toEqual(roles.map((role) => role.label))
    fireEvent.click(screen.getByRole("option", { name: "Quản lý cơ sở" }))

    expect(onValueChange).toHaveBeenLastCalledWith("property_manager")
    expect(trigger).toHaveTextContent("Quản lý cơ sở")

    fireEvent.click(trigger)
    expect(optionLabels()).toEqual(roles.map((role) => role.label))
    expect(screen.getByRole("option", { name: "Quản lý cơ sở" })).toHaveAttribute(
      "data-state",
      "checked",
    )
  })

  it("supports ArrowDown, ArrowUp, Enter, and Escape without losing trigger focus", async () => {
    const onValueChange = vi.fn()
    render(<RoleSelect onValueChange={onValueChange} />)

    const trigger = screen.getByRole("combobox", { name: "Vai trò" })
    trigger.focus()
    fireEvent.keyDown(trigger, { key: "ArrowDown" })
    const technician = await screen.findByRole("option", { name: "Kỹ thuật viên" })
    technician.focus()

    fireEvent.keyDown(technician, { key: "ArrowDown" })
    const manager = screen.getByRole("option", { name: "Quản lý cơ sở" })
    await waitFor(() => expect(manager).toHaveFocus())
    fireEvent.keyDown(manager, { key: "Enter" })
    await waitFor(() => expect(onValueChange).toHaveBeenLastCalledWith("property_manager"))

    fireEvent.keyDown(trigger, { key: "ArrowDown" })
    const selectedManager = await screen.findByRole("option", { name: "Quản lý cơ sở" })
    selectedManager.focus()
    fireEvent.keyDown(selectedManager, { key: "ArrowUp" })
    const previousTechnician = screen.getByRole("option", { name: "Kỹ thuật viên" })
    await waitFor(() => expect(previousTechnician).toHaveFocus())
    fireEvent.keyDown(previousTechnician, { key: "Enter" })
    await waitFor(() => expect(onValueChange).toHaveBeenLastCalledWith("technician"))

    fireEvent.keyDown(trigger, { key: "ArrowDown" })
    const selectedTechnician = await screen.findByRole("option", { name: "Kỹ thuật viên" })
    selectedTechnician.focus()
    fireEvent.keyDown(selectedTechnician, { key: "Escape" })

    await waitFor(() => expect(screen.queryAllByRole("option")).toHaveLength(0))
    expect(trigger).toHaveFocus()
  })
})
