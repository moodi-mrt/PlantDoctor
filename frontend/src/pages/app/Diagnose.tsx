import DiagnoseFlow from "../../components/diagnosis/DiagnoseFlow";
import { PageHeader } from "../../components/ui/ui";
export default function Diagnose() {
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader eyebrow="New diagnosis" title="Diagnose a plant" sub="Photos are analysed by the image model; the treatment plan comes from our curated, source-cited knowledge base." />
      <DiagnoseFlow />
    </div>
  );
}
