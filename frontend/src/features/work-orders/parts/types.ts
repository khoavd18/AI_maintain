import type { Requirement, Reservation } from "@/lib/api/inventory-schemas";

export type PartOption = {
  id: string;
  part_number: string;
  name_vi: string;
  unit_symbol: string;
};

export type LocationOption = { id: string; code: string; name: string };

export type WorkOrderPartsActionContext = {
  workOrderId: string;
  requirements: Requirement[];
  reservations: Reservation[];
  parts: PartOption[];
  locations: LocationOption[];
};
