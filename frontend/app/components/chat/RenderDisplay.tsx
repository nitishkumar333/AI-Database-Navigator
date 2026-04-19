import React, { useContext } from "react";
import { ResultPayload } from "@/app/types/chat";
import { ProductPayload } from "@/app/types/displays";

import ProductDisplay from "./displays/Product/ProductDisplay";
import BoringGenericDisplay from "./displays/Generic/BoringGeneric";
import { DisplayContext } from "../contexts/DisplayContext";

interface RenderDisplayProps {
  payload: ResultPayload;
  index: number;
  messageId: string;
  handleResultPayloadChange: (
    type: string,
    payload: /* eslint-disable @typescript-eslint/no-explicit-any */ any,
    collection_name: string
  ) => void;
}

const RenderDisplay: React.FC<RenderDisplayProps> = ({
  payload,
  index,
  messageId,
  handleResultPayloadChange,
}) => {
  const keyBase = `${index}-${messageId}`;
  const { currentCollectionName } = useContext(DisplayContext);

  const handleResultPayloadChangeWithCollectionName = (
    type: string,
    payload: /* eslint-disable @typescript-eslint/no-explicit-any */ any
  ) => {
    handleResultPayloadChange(type, payload, currentCollectionName);
  };
  console.log(payload);
  switch (payload.type) {
    case "product":
    case "ecommerce":
      return (
        <ProductDisplay
          key={`${keyBase}-product`}
          products={payload.objects as ProductPayload[]}
          handleResultPayloadChange={
            handleResultPayloadChangeWithCollectionName
          }
        />
      );
    case "table":
    case "mapped":
      return (
        <BoringGenericDisplay
          key={`${keyBase}-boring-generic`}
          payload={payload.objects as { [key: string]: string }[]}
        />
      );
    default:
      if (process.env.NODE_ENV === "development") {
        console.warn("Unhandled ResultPayload type:", payload.type);
      }
      return null;
  }
};

export default RenderDisplay;
