import { MobileAssetLookup } from "@/components/mobile-asset-lookup";

export default async function AssetQrLookupPage({
  params,
}: {
  params: Promise<{ lookupToken: string }>;
}) {
  const { lookupToken } = await params;
  return <MobileAssetLookup lookupToken={lookupToken} />;
}
