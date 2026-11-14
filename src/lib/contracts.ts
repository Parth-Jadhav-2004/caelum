import contract from "./ipc-contract.generated.json";

// Deliberately limited JSON Schema vocabulary shared with ipc_contract.py.
// No eval or network schema loading; compatible with the desktop CSP.
export interface Schema {
  type?: string;
  enum?: readonly unknown[];
  anyOf?: readonly Schema[];
  properties?: Record<string, Schema>;
  required?: readonly string[];
  additionalProperties?: boolean | Schema;
  items?: Schema;
}
export const contracts: {
  [K in keyof typeof contract.methods]: { params: Schema; result: Schema };
} = contract.methods;
export function matches(schema: Schema, value: unknown): boolean {
  if (schema.anyOf) return schema.anyOf.some((item) => matches(item, value));
  if (schema.enum) return schema.enum.some((item) => item === value);
  switch (schema.type) {
    case "null":
      return value === null;
    case "boolean":
      return typeof value === "boolean";
    case "string":
      return typeof value === "string";
    case "number":
      return typeof value === "number" && Number.isFinite(value);
    case "array":
      return (
        Array.isArray(value) &&
        !!schema.items &&
        value.every((item) => matches(schema.items!, item))
      );
    case "object": {
      if (!value || typeof value !== "object" || Array.isArray(value))
        return false;
      const record = value as Record<string, unknown>;
      if (schema.required?.some((key) => !Object.hasOwn(record, key)))
        return false;
      return Object.entries(record).every(([key, item]) => {
        if (schema.properties && Object.hasOwn(schema.properties, key))
          return matches(schema.properties[key], item);
        const extra = schema.additionalProperties ?? false;
        return typeof extra === "boolean" ? extra : matches(extra, item);
      });
    }
    default:
      return false;
  }
}
export const validStatus = (value: unknown) => matches(contract.status, value);
