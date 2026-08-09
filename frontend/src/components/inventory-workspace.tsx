"use client";

/**
 * Compatibility facade for the inventory feature entry point.
 *
 * Keep this path stable for existing pages, tests, and downstream imports while
 * the implementation lives with the inventory feature.
 */
export {
  InventoryWorkspace,
  type InventoryWorkspaceView,
} from "@/features/inventory/inventory-workspace";
