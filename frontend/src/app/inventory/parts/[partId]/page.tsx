import { PartDetail } from "@/components/part-detail";

export default async function InventoryPartPage({
  params,
}: {
  params: Promise<{ partId: string }>;
}) {
  const { partId } = await params;
  return <PartDetail partId={partId} />;
}
