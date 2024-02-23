import { h } from "preact";
import { SlButton } from "./shoelace";

export function CollectionTag(props: {
  database: string;
  collection_id: string;
  name: string;
  size: string;
}) {
  const { database, collection_id, name, size } = props;
  return (
    <span style="white-space: nowrap;">
      <SlButton
        size={size}
        pill
        style="white-space: nowrap;"
        href={`/-/datasette-scribe/collection/${database}/${collection_id}`}
      >
        {name}
      </SlButton>
    </span>
  );
}
