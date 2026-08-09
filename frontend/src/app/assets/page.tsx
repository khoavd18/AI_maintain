import { AssetBrowser } from "@/components/asset-browser";
import { PageHeader } from "@/components/page-header";

export default function AssetsPage() {
  return (
    <>
      <PageHeader
        title="Thiết bị"
        description="Lọc danh mục theo rủi ro, mức độ quan trọng và tình trạng bảo trì để chọn đối tượng cần xem xét."
        breadcrumbs={[{ label: "Tổng quan", href: "/" }, { label: "Thiết bị" }]}
      />
      <AssetBrowser />
    </>
  );
}
