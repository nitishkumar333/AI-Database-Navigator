import React from "react";
import { ResultPayload } from "@/app/types/chat";
import { ProductPayload } from "@/app/types/displays";

import ProductDisplay from "./displays/Product/ProductDisplay";
import BoringGenericDisplay from "./displays/Generic/BoringGeneric";

interface RenderDisplayProps {
  payload: ResultPayload;
  onOpenProduct: (product: ProductPayload) => void;
}

const RenderDisplay: React.FC<RenderDisplayProps> = ({ payload, onOpenProduct }) => {
  switch (payload.type) {
    case "product":
      return (
        <ProductDisplay
          products={payload.objects as ProductPayload[]}
          onOpenProduct={onOpenProduct}
        />
      );
    case "table":
      return (
        <BoringGenericDisplay
          payload={payload.objects as Record<string, unknown>[]}
        />
      );
    default:
      return null;
  }
};

export default RenderDisplay;
