import { Loader2 } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Document } from "@/api/types/document";

const DocumentStatusBadge = ({ doc }: { doc: Pick<Document, "status" | "num_chunks"> }) => {
  switch (doc.status) {
    case "pending":
      return <Badge variant="secondary">Queued</Badge>;
    case "processing":
      return (
        <Badge variant="outline">
          <Loader2 className="h-3 w-3 motion-safe:animate-spin" />
          Processing
        </Badge>
      );
    case "indexed":
      return <Badge>Ready · {doc.num_chunks}</Badge>;
    case "failed":
      return <Badge variant="destructive">Failed</Badge>;
  }
};

export default DocumentStatusBadge;
