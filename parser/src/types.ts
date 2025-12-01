export interface ComponentInfo {
  name: string;
  file: string;
  startLine: number;
  endLine: number;
  props: PropInfo[];
  state: StateInfo[];
  hooks: HookInfo[];
  children: string[];
  jsxExpressions: JsxExpressionInfo[];
  isMemoized: boolean;
  isForwardRef: boolean;
  hasDisplayName: boolean;
}

export interface PropInfo {
  name: string;
  type: string;
  hasDefaultValue: boolean;
  defaultValue?: string;
  usedInRender: boolean;
  usedInHooks: string[];
  passedToChildren: ChildPropPass[];
}

export interface ChildPropPass {
  childComponent: string;
  asPropName: string;
  transformed: boolean;
  transformationType?: string;
}

export interface StateInfo {
  name: string;
  setter: string;
  initialValue: string;
  type: string;
  line: number;
  usageLocations: UsageLocation[];
  setterUsageLocations: UsageLocation[];
}

export interface UsageLocation {
  line: number;
  context: "render" | "hook" | "callback" | "effect" | "event-handler";
  hookType?: string;
}

export interface HookInfo {
  type: string;
  line: number;
  dependencies: DependencyInfo[] | null; // null = no array provided
  bodyReferences: string[];
  returnValue?: string;
  isCustomHook: boolean;
}

export interface DependencyInfo {
  name: string;
  isStable: boolean;
  stabilityReason: string;
  definedAt?: number; // line number
  type: "state" | "prop" | "ref" | "callback" | "context" | "external" | "unknown";
}

export interface JsxExpressionInfo {
  type: "inline_function" | "inline_object" | "inline_array" | "ternary" | "logical" | "call_expression";
  line: number;
  propName: string;
  passedToComponent: string | null;
  isComponentMemoized: boolean;
  sourceText: string;
  capturedVariables: CapturedVariable[];
}

export interface CapturedVariable {
  name: string;
  type: "state" | "prop" | "ref" | "local" | "imported" | "unknown";
  isStable: boolean;
}

export interface ParseResult {
  success: boolean;
  components: ComponentInfo[];
  imports: ImportInfo[];
  exports: ExportInfo[];
  errors: ParseError[];
  metadata: FileMetadata;
}

export interface ImportInfo {
  source: string;
  specifiers: string[];
  isDefault: boolean;
  isNamespace: boolean;
  line: number;
}

export interface ExportInfo {
  name: string;
  isDefault: boolean;
  line: number;
}

export interface ParseError {
  message: string;
  line?: number;
  column?: number;
}

export interface FileMetadata {
  totalLines: number;
  totalComponents: number;
  hasTypeScript: boolean;
  hasJsx: boolean;
}
