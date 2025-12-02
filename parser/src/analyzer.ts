import * as parser from '@babel/parser';
import _traverse, { NodePath } from '@babel/traverse';
import * as t from '@babel/types';
import type {
  CapturedVariable,
  ComponentInfo,
  DependencyInfo,
  ExportInfo,
  FileMetadata,
  HookInfo,
  ImportInfo,
  JsxExpressionInfo,
  ParseError,
  ParseResult,
  PropInfo, StateInfo
} from "./types.js";

// @ts-ignore - Babel traverse has ESM/CJS interop issues
const traverse = _traverse.default || _traverse;

export class ReactAstAnalyzer {
  private components: Map<string, ComponentInfo> = new Map();

  /**
   * Main entry point - parse code and return structured data
   */
  parse(code: string, filename: string = "component.tsx"): ParseResult {
    const errors: ParseError[] = [];
    const components: ComponentInfo[] = [];
    const imports: ImportInfo[] = [];
    const exports: ExportInfo[] = [];

    try {
      // Parse with Babel - include all modern JS/TS/React plugins
      const ast = parser.parse(code, {
        sourceType: 'module',
        plugins: [
          'jsx',
          'typescript',
          ['decorators', { decoratorsBeforeExport: true }],
          'classProperties',
          'classPrivateProperties',
          'classPrivateMethods',
          'exportDefaultFrom',
          'exportNamespaceFrom',
          'dynamicImport',
          'nullishCoalescingOperator',
          'optionalChaining',
          'optionalCatchBinding',
          'objectRestSpread',
          'asyncGenerators',
          'functionBind',
          'throwExpressions',
          'topLevelAwait',
          'importMeta',
          'bigInt',
          'numericSeparator',
        ]
      });

      // Track line mapping for accurate line numbers
      const lines = code.split('\n');

      // Extract imports, exports, and components
      traverse(ast, {
        ImportDeclaration: (path: any) => {
          imports.push(this.extractImport(path, lines));
        },
        
        ExportNamedDeclaration: (path: any) => {
          exports.push(...this.extractNamedExport(path, lines));
        },
        
        ExportDefaultDeclaration: (path: any) => {
          exports.push(this.extractDefaultExport(path, lines));
        },

        // Find function declaration components
        FunctionDeclaration: (path: any) => {
          if (this.isReactComponent(path.node.id?.name)) {
            const component = this.analyzeComponent(path, code, lines);
            if (component) {
              this.components.set(component.name, component);
            }
          }
        },

        // Find variable declaration components (arrow functions, memo, etc.)
        VariableDeclarator: (path: any) => {
          const id = path.node.id;
          if (t.isIdentifier(id) && this.isReactComponent(id.name)) {
            const init = path.node.init;
            if (t.isArrowFunctionExpression(init) || 
                t.isFunctionExpression(init) ||
                (t.isCallExpression(init) && this.isReactHOC(init))) {
              const component = this.analyzeComponent(path, code, lines);
              if (component) {
                this.components.set(component.name, component);
              }
            }
          }
        }
      });

      components.push(...Array.from(this.components.values()));

      const metadata: FileMetadata = {
        totalLines: lines.length,
        totalComponents: components.length,
        hasTypeScript: filename.endsWith('.ts') || filename.endsWith('.tsx'),
        hasJsx: filename.endsWith('.jsx') || filename.endsWith('.tsx')
      };

      return {
        success: true,
        components,
        imports,
        exports,
        errors,
        metadata
      };
    } catch (error) {
      errors.push({
        message: error instanceof Error ? error.message : String(error)
      });

      return {
        success: false,
        components: [],
        imports,
        exports,
        errors,
        metadata: {
          totalLines: code.split('\n').length,
          totalComponents: 0,
          hasTypeScript: filename.endsWith('.ts') || filename.endsWith('.tsx'),
          hasJsx: filename.endsWith('.jsx') || filename.endsWith('.tsx')
        }
      };
    }
  }

  /**
   * Extract import information
   */
  private extractImport(path: NodePath<t.ImportDeclaration>, lines: string[]): ImportInfo {
    const node = path.node;
    const source = node.source.value;
    const specifiers: string[] = [];
    let isDefault = false;
    let isNamespace = false;

    node.specifiers.forEach(spec => {
      if (t.isImportDefaultSpecifier(spec)) {
        specifiers.push(spec.local.name);
        isDefault = true;
      } else if (t.isImportNamespaceSpecifier(spec)) {
        specifiers.push(spec.local.name);
        isNamespace = true;
      } else if (t.isImportSpecifier(spec)) {
        specifiers.push(spec.local.name);
      }
    });

    return {
      source,
      specifiers,
      isDefault,
      isNamespace,
      line: node.loc?.start.line || 1
    };
  }

  /**
   * Extract named export information
   */
  private extractNamedExport(path: NodePath<t.ExportNamedDeclaration>, lines: string[]): ExportInfo[] {
    const node = path.node;
    const exports: ExportInfo[] = [];

    if (node.specifiers) {
      node.specifiers.forEach(spec => {
        if (t.isExportSpecifier(spec)) {
          exports.push({
            name: spec.exported.type === 'Identifier' ? spec.exported.name : spec.exported.value,
            isDefault: false,
            line: node.loc?.start.line || 1
          });
        }
      });
    }

    if (node.declaration) {
      if (t.isFunctionDeclaration(node.declaration) && node.declaration.id) {
        exports.push({
          name: node.declaration.id.name,
          isDefault: false,
          line: node.loc?.start.line || 1
        });
      } else if (t.isVariableDeclaration(node.declaration)) {
        node.declaration.declarations.forEach(decl => {
          if (t.isIdentifier(decl.id)) {
            exports.push({
              name: decl.id.name,
              isDefault: false,
              line: node.loc?.start.line || 1
            });
          }
        });
      }
    }

    return exports;
  }

  /**
   * Extract default export information
   */
  private extractDefaultExport(path: NodePath<t.ExportDefaultDeclaration>, lines: string[]): ExportInfo {
    const node = path.node;
    let name = 'default';

    if (t.isIdentifier(node.declaration)) {
      name = node.declaration.name;
    } else if (t.isFunctionDeclaration(node.declaration) && node.declaration.id) {
      name = node.declaration.id.name;
    }

    return {
      name,
      isDefault: true,
      line: node.loc?.start.line || 1
    };
  }

  /**
   * Check if name looks like a React component
   */
  private isReactComponent(name?: string | null): boolean {
    return !!name && /^[A-Z]/.test(name);
  }

  /**
   * Check if call expression is a React HOC (memo, forwardRef, etc.)
   */
  private isReactHOC(node: t.CallExpression): boolean {
    if (t.isIdentifier(node.callee)) {
      return ['memo', 'forwardRef'].includes(node.callee.name);
    }
    if (t.isMemberExpression(node.callee) && 
        t.isIdentifier(node.callee.object) &&
        t.isIdentifier(node.callee.property)) {
      return node.callee.object.name === 'React' && 
             ['memo', 'forwardRef'].includes(node.callee.property.name);
    }
    return false;
  }

  /**
   * Analyze a component (function or variable declarator)
   */
  private analyzeComponent(
    path: NodePath<t.FunctionDeclaration> | NodePath<t.VariableDeclarator>,
    code: string,
    lines: string[]
  ): ComponentInfo | null {
    try {
      // Get component name
      let name = '';
      let funcNode: t.Function | null = null;
      let isMemoized = false;
      let isForwardRef = false;

      if (path.isFunctionDeclaration()) {
        name = path.node.id?.name || 'AnonymousComponent';
        funcNode = path.node;
      } else if (path.isVariableDeclarator()) {
        const id = path.node.id;
        if (t.isIdentifier(id)) {
          name = id.name;
        }

        const init = path.node.init;
        if (t.isArrowFunctionExpression(init) || t.isFunctionExpression(init)) {
          funcNode = init;
        } else if (t.isCallExpression(init)) {
          // Check for memo/forwardRef
          if (this.isReactHOC(init)) {
            isMemoized = t.isIdentifier(init.callee) && init.callee.name === 'memo';
            isForwardRef = t.isIdentifier(init.callee) && init.callee.name === 'forwardRef';
            const firstArg = init.arguments[0];
            if (t.isArrowFunctionExpression(firstArg) || t.isFunctionExpression(firstArg)) {
              funcNode = firstArg;
            }
          }
        }
      }

      if (!funcNode) return null;

      const startLine = funcNode.loc?.start.line || 1;
      const endLine = funcNode.loc?.end.line || startLine;

      // Extract props
      const props = this.extractProps(funcNode);

      // Extract state, hooks, children, JSX expressions
      const state: StateInfo[] = [];
      const hooks: HookInfo[] = [];
      const children: string[] = [];
      const jsxExpressions: JsxExpressionInfo[] = [];

      // Traverse function body
      const funcPath = path.isVariableDeclarator() ? 
        path.get('init') as NodePath<t.Function> : 
        path as NodePath<t.Function>;

      funcPath.traverse({
        CallExpression: (callPath: any) => {
          const callee = callPath.node.callee;
          if (t.isIdentifier(callee) && callee.name.startsWith('use')) {
            // Extract hook
            const hook = this.extractHook(callPath, funcNode!);
            if (hook) {
              hooks.push(hook);
              
              // If it's useState, also add to state
              if (callee.name === 'useState') {
                const stateVar = this.extractStateFromUseState(callPath);
                if (stateVar) {
                  state.push(stateVar);
                }
              }
            }
          }
        },

        JSXElement: (jsxPath: any) => {
          const openingElement = jsxPath.node.openingElement;
          if (t.isJSXIdentifier(openingElement.name)) {
            const tagName = openingElement.name.name;
            if (/^[A-Z]/.test(tagName)) {
              children.push(tagName);
            }
          }
          
          // Extract inline expressions from attributes
          openingElement.attributes.forEach((attr: any) => {
            if (t.isJSXAttribute(attr) && t.isJSXExpressionContainer(attr.value)) {
              const expr = this.extractJSXExpression(attr, openingElement, funcNode!);
              if (expr) {
                jsxExpressions.push(expr);
              }
            }
          });
        },

        JSXFragment: (jsxPath: any) => {
          // Handle JSX fragments
          jsxPath.traverse({
            JSXElement: (innerPath: any) => {
              const openingElement = innerPath.node.openingElement;
              if (t.isJSXIdentifier(openingElement.name)) {
                const tagName = openingElement.name.name;
                if (/^[A-Z]/.test(tagName)) {
                  children.push(tagName);
                }
              }
            }
          });
        }
      });

      // Check for displayName
      let hasDisplayName = false;
      path.parentPath?.traverse({
        AssignmentExpression: (assignPath: any) => {
          const left = assignPath.node.left;
          if (t.isMemberExpression(left) &&
              t.isIdentifier(left.object) &&
              left.object.name === name &&
              t.isIdentifier(left.property) &&
              left.property.name === 'displayName') {
            hasDisplayName = true;
          }
        }
      });

      return {
        name,
        file: '',
        startLine,
        endLine,
        props,
        state,
        hooks,
        children: [...new Set(children)],
        jsxExpressions,
        isMemoized,
        isForwardRef,
        hasDisplayName
      };
    } catch (error) {
      console.error('Error analyzing component:', error);
      return null;
    }
  }

  /**
   * Extract props from function parameters
   */
  private extractProps(funcNode: t.Function): PropInfo[] {
    const props: PropInfo[] = [];

    if (funcNode.params.length === 0) return props;

    const firstParam = funcNode.params[0];

    // Handle destructured props { user, onClick }
    if (t.isObjectPattern(firstParam)) {
      firstParam.properties.forEach(prop => {
        if (t.isObjectProperty(prop) && t.isIdentifier(prop.key)) {
          props.push({
            name: prop.key.name,
            type: 'unknown',
            hasDefaultValue: t.isAssignmentPattern(prop.value),
            usedInRender: false,
            usedInHooks: [],
            passedToChildren: []
          });
        } else if (t.isRestElement(prop) && t.isIdentifier(prop.argument)) {
          props.push({
            name: prop.argument.name,
            type: 'rest',
            hasDefaultValue: false,
            usedInRender: false,
            usedInHooks: [],
            passedToChildren: []
          });
        }
      });
    } 
    // Handle single props parameter
    else if (t.isIdentifier(firstParam)) {
      props.push({
        name: firstParam.name,
        type: 'object',
        hasDefaultValue: false,
        usedInRender: false,
        usedInHooks: [],
        passedToChildren: []
      });
    }

    return props;
  }

  /**
   * Extract hook information
   */
  private extractHook(path: NodePath<t.CallExpression>, funcNode: t.Function): HookInfo | null {
    const callee = path.node.callee;
    if (!t.isIdentifier(callee)) return null;

    const hookName = callee.name;
    const args = path.node.arguments;

    // Extract dependencies if present
    let dependencies: DependencyInfo[] | null = null;
    let bodyReferences: string[] = [];

    // For hooks with dependency arrays (useEffect, useMemo, useCallback, etc.)
    const depsHooks = ['useEffect', 'useLayoutEffect', 'useMemo', 'useCallback'];
    if (depsHooks.includes(hookName) && args.length >= 2) {
      const depsArg = args[args.length - 1];
      if (t.isArrayExpression(depsArg)) {
        dependencies = this.analyzeDependencies(depsArg, funcNode);
      }
    }

    // Extract body references for hooks with callbacks
    if (args.length > 0 && (t.isArrowFunctionExpression(args[0]) || t.isFunctionExpression(args[0]))) {
      bodyReferences = this.extractBodyReferences(args[0]);
    }

    return {
      type: hookName,
      line: path.node.loc?.start.line || 1,
      dependencies,
      bodyReferences,
      returnValue: undefined,
      isCustomHook: hookName.startsWith('use') && 
        !['useState', 'useEffect', 'useLayoutEffect', 'useContext', 'useReducer', 
          'useCallback', 'useMemo', 'useRef', 'useImperativeHandle'].includes(hookName)
    };
  }

  /**
   * Extract state variable from useState call
   */
  private extractStateFromUseState(path: NodePath<t.CallExpression>): StateInfo | null {
    const parent = path.parentPath;
    if (!parent?.isVariableDeclarator()) return null;

    const id = parent.node.id;
    if (!t.isArrayPattern(id) || id.elements.length < 2) return null;

    const stateElem = id.elements[0];
    const setterElem = id.elements[1];

    if (!t.isIdentifier(stateElem) || !t.isIdentifier(setterElem)) return null;

    const initialValue = path.node.arguments[0];

    return {
      name: stateElem.name,
      setter: setterElem.name,
      initialValue: initialValue ? this.nodeToString(initialValue) : 'undefined',
      type: 'any',
      line: path.node.loc?.start.line || 1,
      usageLocations: [],
      setterUsageLocations: []
    };
  }

  /**
   * Analyze dependency array
   */
  private analyzeDependencies(depsArray: t.ArrayExpression, funcNode: t.Function): DependencyInfo[] {
    const deps: DependencyInfo[] = [];

    depsArray.elements.forEach(elem => {
      if (t.isIdentifier(elem)) {
        const name = elem.name;
        const isStable = this.isDependencyStable(name);
        const depType = this.getDependencyType(name);

        deps.push({
          name,
          isStable: isStable.isStable,
          stabilityReason: isStable.reason,
          type: depType
        });
      }
    });

    return deps;
  }

  /**
   * Determine if a dependency is stable
   */
  private isDependencyStable(name: string): { isStable: boolean; reason: string } {
    // setState functions are stable
    if (name.startsWith('set') && name.length > 3 && /^set[A-Z]/.test(name)) {
      return { isStable: true, reason: 'setState function is stable' };
    }

    // Refs are stable
    if (name.endsWith('Ref') || name.includes('Ref')) {
      return { isStable: true, reason: 'useRef result is stable' };
    }

    // dispatch from useReducer is stable
    if (name === 'dispatch') {
      return { isStable: true, reason: 'dispatch from useReducer is stable' };
    }

    // Props are unstable
    if (/^[a-z]/.test(name) && !name.includes('_')) {
      return { isStable: false, reason: 'Prop value depends on parent' };
    }

    return { isStable: false, reason: 'Variable may be recreated each render' };
  }

  /**
   * Determine the type of a dependency
   */
  private getDependencyType(name: string): DependencyInfo['type'] {
    if (name.startsWith('set') && /^set[A-Z]/.test(name)) {
      return 'state';
    }
    if (name.endsWith('Ref')) {
      return 'ref';
    }
    if (name === 'dispatch') {
      return 'callback';
    }
    if (/^[a-z]/.test(name)) {
      return 'prop';
    }
    return 'unknown';
  }

  /**
   * Extract JSX expression information
   */
  private extractJSXExpression(
    attr: t.JSXAttribute,
    openingElement: t.JSXOpeningElement,
    funcNode: t.Function
  ): JsxExpressionInfo | null {
    if (!t.isJSXExpressionContainer(attr.value)) return null;

    const expr = attr.value.expression;
    if (t.isJSXEmptyExpression(expr)) return null;

    let type: JsxExpressionInfo['type'] | null = null;

    if (t.isArrowFunctionExpression(expr) || t.isFunctionExpression(expr)) {
      type = 'inline_function';
    } else if (t.isObjectExpression(expr)) {
      type = 'inline_object';
    } else if (t.isArrayExpression(expr)) {
      type = 'inline_array';
    } else if (t.isConditionalExpression(expr)) {
      type = 'ternary';
    } else if (t.isLogicalExpression(expr) && (expr.operator === '&&' || expr.operator === '||')) {
      type = 'logical';
    } else if (t.isCallExpression(expr)) {
      type = 'call_expression';
    }

    if (!type) return null;

    const propName = t.isJSXIdentifier(attr.name) ? attr.name.name : 'unknown';
    const componentName = t.isJSXIdentifier(openingElement.name) ? openingElement.name.name : null;
    const isComponentMemoized = componentName ? this.components.get(componentName)?.isMemoized || false : false;

    const capturedVars = this.extractCapturedVariables(expr, funcNode);

    return {
      type,
      line: expr.loc?.start.line || 1,
      propName,
      passedToComponent: componentName,
      isComponentMemoized,
      sourceText: this.nodeToString(expr).slice(0, 100),
      capturedVariables: capturedVars
    };
  }

  /**
   * Extract variables captured by an expression
   */
  private extractCapturedVariables(expr: t.Node, funcNode: t.Function): CapturedVariable[] {
    const captured: CapturedVariable[] = [];
    const identifiers = new Set<string>();

    // Simple recursive walk to collect identifiers
    const walk = (node: any, isRightOfMemberExpr = false) => {
      if (!node || typeof node !== 'object') return;

      if (t.isIdentifier(node) && !isRightOfMemberExpr) {
        identifiers.add(node.name);
      }

      if (t.isMemberExpression(node)) {
        walk(node.object, false);
        walk(node.property, true); // Don't collect property names
        return;
      }

      // Walk children
      for (const key in node) {
        if (key === 'loc' || key === 'start' || key === 'end') continue;
        const child = node[key];
        if (Array.isArray(child)) {
          child.forEach((c) => walk(c, false));
        } else if (child && typeof child === 'object') {
          walk(child, false);
        }
      }
    };

    walk(expr);

    // Filter out keywords and determine types
    const keywords = new Set(['console', 'log', 'map', 'filter', 'reduce', 'forEach', 'return', 'if', 'else']);
    
    identifiers.forEach(name => {
      if (keywords.has(name)) return;

      const isState = name.startsWith('set') || this.looksLikeStateVariable(name);
      const isProp = /^[a-z]/.test(name) && !name.startsWith('set');
      const isStable = name.startsWith('set') || name.endsWith('Ref');

      captured.push({
        name,
        type: isState ? 'state' : isProp ? 'prop' : 'unknown',
        isStable
      });
    });

    return captured;
  }

  /**
   * Extract identifiers referenced in function body
   */
  private extractBodyReferences(funcExpr: t.Function): string[] {
    const refs = new Set<string>();
    const keywords = new Set(['const', 'let', 'var', 'function', 'return', 'if', 'else']);

    // Simple recursive walk to collect identifiers
    const walk = (node: any) => {
      if (!node || typeof node !== 'object') return;

      if (t.isIdentifier(node)) {
        if (!keywords.has(node.name)) {
          refs.add(node.name);
        }
      }

      // Walk children
      for (const key in node) {
        if (key === 'loc' || key === 'start' || key === 'end') continue;
        const child = node[key];
        if (Array.isArray(child)) {
          child.forEach(walk);
        } else if (child && typeof child === 'object') {
          walk(child);
        }
      }
    };

    walk(funcExpr.body);
    return Array.from(refs);
  }

  /**
   * Check if name looks like a state variable
   */
  private looksLikeStateVariable(name: string): boolean {
    return /^[a-z]/.test(name) && !name.startsWith('set');
  }

  /**
   * Convert AST node to string representation
   */
  private nodeToString(node: t.Node): string {
    try {
      if (t.isStringLiteral(node)) return `"${node.value}"`;
      if (t.isNumericLiteral(node)) return String(node.value);
      if (t.isBooleanLiteral(node)) return String(node.value);
      if (t.isNullLiteral(node)) return 'null';
      if (t.isIdentifier(node)) return node.name;
      if (t.isArrayExpression(node)) return '[]';
      if (t.isObjectExpression(node)) return '{}';
      if (t.isArrowFunctionExpression(node)) return '() => {}';
      return '<complex>';
    } catch {
      return '<unknown>';
    }
  }
}
