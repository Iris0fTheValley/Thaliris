window.__ModuleLoader__.load({
	id: "@thaliris/dsh-plugin",
	factory: (require) => {
		var module = { exports: {} };
		var exports = module.exports;
		Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
		let _deepseek_ai_dsh_client_store = require("@deepseek-ai/dsh-client-store");
		let react = require("react");
		let _deepseek_ai_dsh_client_ui_primitives = require("@deepseek-ai/dsh-client-ui-primitives");
		let react_jsx_runtime = require("react/jsx-runtime");
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/core.js
		var _a$1;
		function $constructor(name, initializer, params) {
			function init(inst, def) {
				if (!inst._zod) Object.defineProperty(inst, "_zod", {
					value: {
						def,
						constr: _,
						traits: /* @__PURE__ */ new Set()
					},
					enumerable: false
				});
				if (inst._zod.traits.has(name)) return;
				inst._zod.traits.add(name);
				initializer(inst, def);
				const proto = _.prototype;
				const keys = Object.keys(proto);
				for (let i = 0; i < keys.length; i++) {
					const k = keys[i];
					if (!(k in inst)) inst[k] = proto[k].bind(inst);
				}
			}
			const Parent = params?.Parent ?? Object;
			class Definition extends Parent {}
			Object.defineProperty(Definition, "name", { value: name });
			function _(def) {
				var _a;
				const inst = params?.Parent ? new Definition() : this;
				init(inst, def);
				(_a = inst._zod).deferred ?? (_a.deferred = []);
				for (const fn of inst._zod.deferred) fn();
				return inst;
			}
			Object.defineProperty(_, "init", { value: init });
			Object.defineProperty(_, Symbol.hasInstance, { value: (inst) => {
				if (params?.Parent && inst instanceof params.Parent) return true;
				return inst?._zod?.traits?.has(name);
			} });
			Object.defineProperty(_, "name", { value: name });
			return _;
		}
		var $ZodAsyncError = class extends Error {
			constructor() {
				super(`Encountered Promise during synchronous parse. Use .parseAsync() instead.`);
			}
		};
		var $ZodEncodeError = class extends Error {
			constructor(name) {
				super(`Encountered unidirectional transform during encode: ${name}`);
				this.name = "ZodEncodeError";
			}
		};
		(_a$1 = globalThis).__zod_globalConfig ?? (_a$1.__zod_globalConfig = {});
		const globalConfig = globalThis.__zod_globalConfig;
		function config(newConfig) {
			if (newConfig) Object.assign(globalConfig, newConfig);
			return globalConfig;
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/util.js
		function jsonStringifyReplacer(_, value) {
			if (typeof value === "bigint") return value.toString();
			return value;
		}
		function nullish(input) {
			return input === null || input === void 0;
		}
		function cleanRegex(source) {
			const start = source.startsWith("^") ? 1 : 0;
			const end = source.endsWith("$") ? source.length - 1 : source.length;
			return source.slice(start, end);
		}
		function floatSafeRemainder(val, step) {
			const ratio = val / step;
			const roundedRatio = Math.round(ratio);
			const tolerance = Number.EPSILON * Math.max(Math.abs(ratio), 1);
			if (Math.abs(ratio - roundedRatio) < tolerance) return 0;
			return ratio - roundedRatio;
		}
		const EVALUATING = /* @__PURE__*/ Symbol("evaluating");
		function defineLazy(object, key, getter) {
			let value = void 0;
			Object.defineProperty(object, key, {
				get() {
					if (value === EVALUATING) return;
					if (value === void 0) {
						value = EVALUATING;
						value = getter();
					}
					return value;
				},
				set(v) {
					Object.defineProperty(object, key, { value: v });
				},
				configurable: true
			});
		}
		function mergeDefs(...defs) {
			const mergedDescriptors = {};
			for (const def of defs) Object.assign(mergedDescriptors, Object.getOwnPropertyDescriptors(def));
			return Object.defineProperties({}, mergedDescriptors);
		}
		function slugify(input) {
			return input.toLowerCase().trim().replace(/[^\w\s-]/g, "").replace(/[\s_-]+/g, "-").replace(/^-+|-+$/g, "");
		}
		const captureStackTrace = "captureStackTrace" in Error ? Error.captureStackTrace : (..._args) => {};
		function isObject(data) {
			return typeof data === "object" && data !== null && !Array.isArray(data);
		}
		function isPlainObject(o) {
			if (isObject(o) === false) return false;
			const ctor = o.constructor;
			if (ctor === void 0) return true;
			if (typeof ctor !== "function") return true;
			const prot = ctor.prototype;
			if (isObject(prot) === false) return false;
			if (Object.prototype.hasOwnProperty.call(prot, "isPrototypeOf") === false) return false;
			return true;
		}
		function shallowClone(o) {
			if (isPlainObject(o)) return { ...o };
			if (Array.isArray(o)) return [...o];
			if (o instanceof Map) return new Map(o);
			if (o instanceof Set) return new Set(o);
			return o;
		}
		function escapeRegex(str) {
			return str.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
		}
		function clone(inst, def, params) {
			const cl = new inst._zod.constr(def ?? inst._zod.def);
			if (!def || params?.parent) cl._zod.parent = inst;
			return cl;
		}
		function normalizeParams(_params) {
			const params = _params;
			if (!params) return {};
			if (typeof params === "string") return { error: () => params };
			if (params?.message !== void 0) {
				if (params?.error !== void 0) throw new Error("Cannot specify both `message` and `error` params");
				params.error = params.message;
			}
			delete params.message;
			if (typeof params.error === "string") return {
				...params,
				error: () => params.error
			};
			return params;
		}
		const NUMBER_FORMAT_RANGES = {
			safeint: [Number.MIN_SAFE_INTEGER, Number.MAX_SAFE_INTEGER],
			int32: [-2147483648, 2147483647],
			uint32: [0, 4294967295],
			float32: [-34028234663852886e22, 34028234663852886e22],
			float64: [-Number.MAX_VALUE, Number.MAX_VALUE]
		};
		function aborted(x, startIndex = 0) {
			if (x.aborted === true) return true;
			for (let i = startIndex; i < x.issues.length; i++) if (x.issues[i]?.continue !== true) return true;
			return false;
		}
		function explicitlyAborted(x, startIndex = 0) {
			if (x.aborted === true) return true;
			for (let i = startIndex; i < x.issues.length; i++) if (x.issues[i]?.continue === false) return true;
			return false;
		}
		function prefixIssues(path, issues) {
			return issues.map((iss) => {
				var _a;
				(_a = iss).path ?? (_a.path = []);
				iss.path.unshift(path);
				return iss;
			});
		}
		function unwrapMessage(message) {
			return typeof message === "string" ? message : message?.message;
		}
		function finalizeIssue(iss, ctx, config) {
			const message = iss.message ? iss.message : unwrapMessage(iss.inst?._zod.def?.error?.(iss)) ?? unwrapMessage(ctx?.error?.(iss)) ?? unwrapMessage(config.customError?.(iss)) ?? unwrapMessage(config.localeError?.(iss)) ?? "Invalid input";
			const { inst: _inst, continue: _continue, input: _input, ...rest } = iss;
			rest.path ?? (rest.path = []);
			rest.message = message;
			if (ctx?.reportInput) rest.input = _input;
			return rest;
		}
		function getLengthableOrigin(input) {
			if (Array.isArray(input)) return "array";
			if (typeof input === "string") return "string";
			return "unknown";
		}
		function issue(...args) {
			const [iss, input, inst] = args;
			if (typeof iss === "string") return {
				message: iss,
				code: "custom",
				input,
				inst
			};
			return { ...iss };
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/errors.js
		const initializer$1 = (inst, def) => {
			inst.name = "$ZodError";
			Object.defineProperty(inst, "_zod", {
				value: inst._zod,
				enumerable: false
			});
			Object.defineProperty(inst, "issues", {
				value: def,
				enumerable: false
			});
			inst.message = JSON.stringify(def, jsonStringifyReplacer, 2);
			Object.defineProperty(inst, "toString", {
				value: () => inst.message,
				enumerable: false
			});
		};
		const $ZodError = $constructor("$ZodError", initializer$1);
		const $ZodRealError = $constructor("$ZodError", initializer$1, { Parent: Error });
		function flattenError(error, mapper = (issue) => issue.message) {
			const fieldErrors = {};
			const formErrors = [];
			for (const sub of error.issues) if (sub.path.length > 0) {
				fieldErrors[sub.path[0]] = fieldErrors[sub.path[0]] || [];
				fieldErrors[sub.path[0]].push(mapper(sub));
			} else formErrors.push(mapper(sub));
			return {
				formErrors,
				fieldErrors
			};
		}
		function formatError(error, mapper = (issue) => issue.message) {
			const fieldErrors = { _errors: [] };
			const processError = (error, path = []) => {
				for (const issue of error.issues) if (issue.code === "invalid_union" && issue.errors.length) issue.errors.map((issues) => processError({ issues }, [...path, ...issue.path]));
				else if (issue.code === "invalid_key") processError({ issues: issue.issues }, [...path, ...issue.path]);
				else if (issue.code === "invalid_element") processError({ issues: issue.issues }, [...path, ...issue.path]);
				else {
					const fullpath = [...path, ...issue.path];
					if (fullpath.length === 0) fieldErrors._errors.push(mapper(issue));
					else {
						let curr = fieldErrors;
						let i = 0;
						while (i < fullpath.length) {
							const el = fullpath[i];
							if (!(i === fullpath.length - 1)) curr[el] = curr[el] || { _errors: [] };
							else {
								curr[el] = curr[el] || { _errors: [] };
								curr[el]._errors.push(mapper(issue));
							}
							curr = curr[el];
							i++;
						}
					}
				}
			};
			processError(error);
			return fieldErrors;
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/parse.js
		const _parse = (_Err) => (schema, value, _ctx, _params) => {
			const ctx = _ctx ? {
				..._ctx,
				async: false
			} : { async: false };
			const result = schema._zod.run({
				value,
				issues: []
			}, ctx);
			if (result instanceof Promise) throw new $ZodAsyncError();
			if (result.issues.length) {
				const e = new ((_params?.Err) ?? _Err)(result.issues.map((iss) => finalizeIssue(iss, ctx, config())));
				captureStackTrace(e, _params?.callee);
				throw e;
			}
			return result.value;
		};
		const _parseAsync = (_Err) => async (schema, value, _ctx, params) => {
			const ctx = _ctx ? {
				..._ctx,
				async: true
			} : { async: true };
			let result = schema._zod.run({
				value,
				issues: []
			}, ctx);
			if (result instanceof Promise) result = await result;
			if (result.issues.length) {
				const e = new ((params?.Err) ?? _Err)(result.issues.map((iss) => finalizeIssue(iss, ctx, config())));
				captureStackTrace(e, params?.callee);
				throw e;
			}
			return result.value;
		};
		const _safeParse = (_Err) => (schema, value, _ctx) => {
			const ctx = _ctx ? {
				..._ctx,
				async: false
			} : { async: false };
			const result = schema._zod.run({
				value,
				issues: []
			}, ctx);
			if (result instanceof Promise) throw new $ZodAsyncError();
			return result.issues.length ? {
				success: false,
				error: new (_Err ?? $ZodError)(result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
			} : {
				success: true,
				data: result.value
			};
		};
		const safeParse$1 = /* @__PURE__*/ _safeParse($ZodRealError);
		const _safeParseAsync = (_Err) => async (schema, value, _ctx) => {
			const ctx = _ctx ? {
				..._ctx,
				async: true
			} : { async: true };
			let result = schema._zod.run({
				value,
				issues: []
			}, ctx);
			if (result instanceof Promise) result = await result;
			return result.issues.length ? {
				success: false,
				error: new _Err(result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
			} : {
				success: true,
				data: result.value
			};
		};
		const safeParseAsync$1 = /* @__PURE__*/ _safeParseAsync($ZodRealError);
		const _encode = (_Err) => (schema, value, _ctx) => {
			const ctx = _ctx ? {
				..._ctx,
				direction: "backward"
			} : { direction: "backward" };
			return _parse(_Err)(schema, value, ctx);
		};
		const _decode = (_Err) => (schema, value, _ctx) => {
			return _parse(_Err)(schema, value, _ctx);
		};
		const _encodeAsync = (_Err) => async (schema, value, _ctx) => {
			const ctx = _ctx ? {
				..._ctx,
				direction: "backward"
			} : { direction: "backward" };
			return _parseAsync(_Err)(schema, value, ctx);
		};
		const _decodeAsync = (_Err) => async (schema, value, _ctx) => {
			return _parseAsync(_Err)(schema, value, _ctx);
		};
		const _safeEncode = (_Err) => (schema, value, _ctx) => {
			const ctx = _ctx ? {
				..._ctx,
				direction: "backward"
			} : { direction: "backward" };
			return _safeParse(_Err)(schema, value, ctx);
		};
		const _safeDecode = (_Err) => (schema, value, _ctx) => {
			return _safeParse(_Err)(schema, value, _ctx);
		};
		const _safeEncodeAsync = (_Err) => async (schema, value, _ctx) => {
			const ctx = _ctx ? {
				..._ctx,
				direction: "backward"
			} : { direction: "backward" };
			return _safeParseAsync(_Err)(schema, value, ctx);
		};
		const _safeDecodeAsync = (_Err) => async (schema, value, _ctx) => {
			return _safeParseAsync(_Err)(schema, value, _ctx);
		};
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/regexes.js
		/**
		* @deprecated CUID v1 is deprecated by its authors due to information leakage
		* (timestamps embedded in the id). Use {@link cuid2} instead.
		* See https://github.com/paralleldrive/cuid.
		*/
		const cuid = /^[cC][0-9a-z]{6,}$/;
		const cuid2 = /^[0-9a-z]+$/;
		const ulid = /^[0-9A-HJKMNP-TV-Za-hjkmnp-tv-z]{26}$/;
		const xid = /^[0-9a-vA-V]{20}$/;
		const ksuid = /^[A-Za-z0-9]{27}$/;
		const nanoid = /^[a-zA-Z0-9_-]{21}$/;
		/** ISO 8601-1 duration regex. Does not support the 8601-2 extensions like negative durations or fractional/negative components. */
		const duration$1 = /^P(?:(\d+W)|(?!.*W)(?=\d|T\d)(\d+Y)?(\d+M)?(\d+D)?(T(?=\d)(\d+H)?(\d+M)?(\d+([.,]\d+)?S)?)?)$/;
		/** A regex for any UUID-like identifier: 8-4-4-4-12 hex pattern */
		const guid = /^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})$/;
		/** Returns a regex for validating an RFC 9562/4122 UUID.
		*
		* @param version Optionally specify a version 1-8. If no version is specified, all versions are supported. */
		const uuid = (version) => {
			if (!version) return /^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-8][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}|00000000-0000-0000-0000-000000000000|ffffffff-ffff-ffff-ffff-ffffffffffff)$/;
			return new RegExp(`^([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-${version}[0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12})$`);
		};
		/** Practical email validation */
		const email = /^(?!\.)(?!.*\.\.)([A-Za-z0-9_'+\-\.]*)[A-Za-z0-9_+-]@([A-Za-z0-9][A-Za-z0-9\-]*\.)+[A-Za-z]{2,}$/;
		const _emoji$1 = `^(\\p{Extended_Pictographic}|\\p{Emoji_Component})+$`;
		function emoji() {
			return new RegExp(_emoji$1, "u");
		}
		const ipv4 = /^(?:(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(?:25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])$/;
		const ipv6 = /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,7}:|([0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|([0-9a-fA-F]{1,4}:){1,5}(:[0-9a-fA-F]{1,4}){1,2}|([0-9a-fA-F]{1,4}:){1,4}(:[0-9a-fA-F]{1,4}){1,3}|([0-9a-fA-F]{1,4}:){1,3}(:[0-9a-fA-F]{1,4}){1,4}|([0-9a-fA-F]{1,4}:){1,2}(:[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:((:[0-9a-fA-F]{1,4}){1,6})|:((:[0-9a-fA-F]{1,4}){1,7}|:))$/;
		const cidrv4 = /^((25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\.){3}(25[0-5]|2[0-4][0-9]|1[0-9][0-9]|[1-9][0-9]|[0-9])\/([0-9]|[1-2][0-9]|3[0-2])$/;
		const cidrv6 = /^(([0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|::|([0-9a-fA-F]{1,4})?::([0-9a-fA-F]{1,4}:?){0,6})\/(12[0-8]|1[01][0-9]|[1-9]?[0-9])$/;
		const base64 = /^$|^(?:[0-9a-zA-Z+/]{4})*(?:(?:[0-9a-zA-Z+/]{2}==)|(?:[0-9a-zA-Z+/]{3}=))?$/;
		const base64url = /^[A-Za-z0-9_-]*$/;
		const httpProtocol = /^https?$/;
		const e164 = /^\+[1-9]\d{6,14}$/;
		const dateSource = `(?:(?:\\d\\d[2468][048]|\\d\\d[13579][26]|\\d\\d0[48]|[02468][048]00|[13579][26]00)-02-29|\\d{4}-(?:(?:0[13578]|1[02])-(?:0[1-9]|[12]\\d|3[01])|(?:0[469]|11)-(?:0[1-9]|[12]\\d|30)|(?:02)-(?:0[1-9]|1\\d|2[0-8])))`;
		const date$1 = /*@__PURE__*/ new RegExp(`^${dateSource}$`);
		function timeSource(args) {
			const hhmm = `(?:[01]\\d|2[0-3]):[0-5]\\d`;
			return typeof args.precision === "number" ? args.precision === -1 ? `${hhmm}` : args.precision === 0 ? `${hhmm}:[0-5]\\d` : `${hhmm}:[0-5]\\d\\.\\d{${args.precision}}` : `${hhmm}(?::[0-5]\\d(?:\\.\\d+)?)?`;
		}
		function time$1(args) {
			return new RegExp(`^${timeSource(args)}$`);
		}
		function datetime$1(args) {
			const time = timeSource({ precision: args.precision });
			const opts = ["Z"];
			if (args.local) opts.push("");
			if (args.offset) opts.push(`([+-](?:[01]\\d|2[0-3]):[0-5]\\d)`);
			const timeRegex = `${time}(?:${opts.join("|")})`;
			return new RegExp(`^${dateSource}T(?:${timeRegex})$`);
		}
		const string$1 = (params) => {
			const regex = params ? `[\\s\\S]{${params?.minimum ?? 0},${params?.maximum ?? ""}}` : `[\\s\\S]*`;
			return new RegExp(`^${regex}$`);
		};
		const integer = /^-?\d+$/;
		const number$1 = /^-?\d+(?:\.\d+)?$/;
		const boolean$1 = /^(?:true|false)$/i;
		const _null$2 = /^null$/i;
		const lowercase = /^[^A-Z]*$/;
		const uppercase = /^[^a-z]*$/;
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/checks.js
		const $ZodCheck = /*@__PURE__*/ $constructor("$ZodCheck", (inst, def) => {
			var _a;
			inst._zod ?? (inst._zod = {});
			inst._zod.def = def;
			(_a = inst._zod).onattach ?? (_a.onattach = []);
		});
		const numericOriginMap = {
			number: "number",
			bigint: "bigint",
			object: "date"
		};
		const $ZodCheckLessThan = /*@__PURE__*/ $constructor("$ZodCheckLessThan", (inst, def) => {
			$ZodCheck.init(inst, def);
			const origin = numericOriginMap[typeof def.value];
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				const curr = (def.inclusive ? bag.maximum : bag.exclusiveMaximum) ?? Number.POSITIVE_INFINITY;
				if (def.value < curr) if (def.inclusive) bag.maximum = def.value;
				else bag.exclusiveMaximum = def.value;
			});
			inst._zod.check = (payload) => {
				if (def.inclusive ? payload.value <= def.value : payload.value < def.value) return;
				payload.issues.push({
					origin,
					code: "too_big",
					maximum: typeof def.value === "object" ? def.value.getTime() : def.value,
					input: payload.value,
					inclusive: def.inclusive,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckGreaterThan = /*@__PURE__*/ $constructor("$ZodCheckGreaterThan", (inst, def) => {
			$ZodCheck.init(inst, def);
			const origin = numericOriginMap[typeof def.value];
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				const curr = (def.inclusive ? bag.minimum : bag.exclusiveMinimum) ?? Number.NEGATIVE_INFINITY;
				if (def.value > curr) if (def.inclusive) bag.minimum = def.value;
				else bag.exclusiveMinimum = def.value;
			});
			inst._zod.check = (payload) => {
				if (def.inclusive ? payload.value >= def.value : payload.value > def.value) return;
				payload.issues.push({
					origin,
					code: "too_small",
					minimum: typeof def.value === "object" ? def.value.getTime() : def.value,
					input: payload.value,
					inclusive: def.inclusive,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckMultipleOf = /*@__PURE__*/ $constructor("$ZodCheckMultipleOf", (inst, def) => {
			$ZodCheck.init(inst, def);
			inst._zod.onattach.push((inst) => {
				var _a;
				(_a = inst._zod.bag).multipleOf ?? (_a.multipleOf = def.value);
			});
			inst._zod.check = (payload) => {
				if (typeof payload.value !== typeof def.value) throw new Error("Cannot mix number and bigint in multiple_of check.");
				if (typeof payload.value === "bigint" ? payload.value % def.value === BigInt(0) : floatSafeRemainder(payload.value, def.value) === 0) return;
				payload.issues.push({
					origin: typeof payload.value,
					code: "not_multiple_of",
					divisor: def.value,
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckNumberFormat = /*@__PURE__*/ $constructor("$ZodCheckNumberFormat", (inst, def) => {
			$ZodCheck.init(inst, def);
			def.format = def.format || "float64";
			const isInt = def.format?.includes("int");
			const origin = isInt ? "int" : "number";
			const [minimum, maximum] = NUMBER_FORMAT_RANGES[def.format];
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				bag.format = def.format;
				bag.minimum = minimum;
				bag.maximum = maximum;
				if (isInt) bag.pattern = integer;
			});
			inst._zod.check = (payload) => {
				const input = payload.value;
				if (isInt) {
					if (!Number.isInteger(input)) {
						payload.issues.push({
							expected: origin,
							format: def.format,
							code: "invalid_type",
							continue: false,
							input,
							inst
						});
						return;
					}
					if (!Number.isSafeInteger(input)) {
						if (input > 0) payload.issues.push({
							input,
							code: "too_big",
							maximum: Number.MAX_SAFE_INTEGER,
							note: "Integers must be within the safe integer range.",
							inst,
							origin,
							inclusive: true,
							continue: !def.abort
						});
						else payload.issues.push({
							input,
							code: "too_small",
							minimum: Number.MIN_SAFE_INTEGER,
							note: "Integers must be within the safe integer range.",
							inst,
							origin,
							inclusive: true,
							continue: !def.abort
						});
						return;
					}
				}
				if (input < minimum) payload.issues.push({
					origin: "number",
					input,
					code: "too_small",
					minimum,
					inclusive: true,
					inst,
					continue: !def.abort
				});
				if (input > maximum) payload.issues.push({
					origin: "number",
					input,
					code: "too_big",
					maximum,
					inclusive: true,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckMaxLength = /*@__PURE__*/ $constructor("$ZodCheckMaxLength", (inst, def) => {
			var _a;
			$ZodCheck.init(inst, def);
			(_a = inst._zod.def).when ?? (_a.when = (payload) => {
				const val = payload.value;
				return !nullish(val) && val.length !== void 0;
			});
			inst._zod.onattach.push((inst) => {
				const curr = inst._zod.bag.maximum ?? Number.POSITIVE_INFINITY;
				if (def.maximum < curr) inst._zod.bag.maximum = def.maximum;
			});
			inst._zod.check = (payload) => {
				const input = payload.value;
				if (input.length <= def.maximum) return;
				const origin = getLengthableOrigin(input);
				payload.issues.push({
					origin,
					code: "too_big",
					maximum: def.maximum,
					inclusive: true,
					input,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckMinLength = /*@__PURE__*/ $constructor("$ZodCheckMinLength", (inst, def) => {
			var _a;
			$ZodCheck.init(inst, def);
			(_a = inst._zod.def).when ?? (_a.when = (payload) => {
				const val = payload.value;
				return !nullish(val) && val.length !== void 0;
			});
			inst._zod.onattach.push((inst) => {
				const curr = inst._zod.bag.minimum ?? Number.NEGATIVE_INFINITY;
				if (def.minimum > curr) inst._zod.bag.minimum = def.minimum;
			});
			inst._zod.check = (payload) => {
				const input = payload.value;
				if (input.length >= def.minimum) return;
				const origin = getLengthableOrigin(input);
				payload.issues.push({
					origin,
					code: "too_small",
					minimum: def.minimum,
					inclusive: true,
					input,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckLengthEquals = /*@__PURE__*/ $constructor("$ZodCheckLengthEquals", (inst, def) => {
			var _a;
			$ZodCheck.init(inst, def);
			(_a = inst._zod.def).when ?? (_a.when = (payload) => {
				const val = payload.value;
				return !nullish(val) && val.length !== void 0;
			});
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				bag.minimum = def.length;
				bag.maximum = def.length;
				bag.length = def.length;
			});
			inst._zod.check = (payload) => {
				const input = payload.value;
				const length = input.length;
				if (length === def.length) return;
				const origin = getLengthableOrigin(input);
				const tooBig = length > def.length;
				payload.issues.push({
					origin,
					...tooBig ? {
						code: "too_big",
						maximum: def.length
					} : {
						code: "too_small",
						minimum: def.length
					},
					inclusive: true,
					exact: true,
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckStringFormat = /*@__PURE__*/ $constructor("$ZodCheckStringFormat", (inst, def) => {
			var _a, _b;
			$ZodCheck.init(inst, def);
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				bag.format = def.format;
				if (def.pattern) {
					bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
					bag.patterns.add(def.pattern);
				}
			});
			if (def.pattern) (_a = inst._zod).check ?? (_a.check = (payload) => {
				def.pattern.lastIndex = 0;
				if (def.pattern.test(payload.value)) return;
				payload.issues.push({
					origin: "string",
					code: "invalid_format",
					format: def.format,
					input: payload.value,
					...def.pattern ? { pattern: def.pattern.toString() } : {},
					inst,
					continue: !def.abort
				});
			});
			else (_b = inst._zod).check ?? (_b.check = () => {});
		});
		const $ZodCheckRegex = /*@__PURE__*/ $constructor("$ZodCheckRegex", (inst, def) => {
			$ZodCheckStringFormat.init(inst, def);
			inst._zod.check = (payload) => {
				def.pattern.lastIndex = 0;
				if (def.pattern.test(payload.value)) return;
				payload.issues.push({
					origin: "string",
					code: "invalid_format",
					format: "regex",
					input: payload.value,
					pattern: def.pattern.toString(),
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckLowerCase = /*@__PURE__*/ $constructor("$ZodCheckLowerCase", (inst, def) => {
			def.pattern ?? (def.pattern = lowercase);
			$ZodCheckStringFormat.init(inst, def);
		});
		const $ZodCheckUpperCase = /*@__PURE__*/ $constructor("$ZodCheckUpperCase", (inst, def) => {
			def.pattern ?? (def.pattern = uppercase);
			$ZodCheckStringFormat.init(inst, def);
		});
		const $ZodCheckIncludes = /*@__PURE__*/ $constructor("$ZodCheckIncludes", (inst, def) => {
			$ZodCheck.init(inst, def);
			const escapedRegex = escapeRegex(def.includes);
			const pattern = new RegExp(typeof def.position === "number" ? `^.{${def.position}}${escapedRegex}` : escapedRegex);
			def.pattern = pattern;
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
				bag.patterns.add(pattern);
			});
			inst._zod.check = (payload) => {
				if (payload.value.includes(def.includes, def.position)) return;
				payload.issues.push({
					origin: "string",
					code: "invalid_format",
					format: "includes",
					includes: def.includes,
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckStartsWith = /*@__PURE__*/ $constructor("$ZodCheckStartsWith", (inst, def) => {
			$ZodCheck.init(inst, def);
			const pattern = new RegExp(`^${escapeRegex(def.prefix)}.*`);
			def.pattern ?? (def.pattern = pattern);
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
				bag.patterns.add(pattern);
			});
			inst._zod.check = (payload) => {
				if (payload.value.startsWith(def.prefix)) return;
				payload.issues.push({
					origin: "string",
					code: "invalid_format",
					format: "starts_with",
					prefix: def.prefix,
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckEndsWith = /*@__PURE__*/ $constructor("$ZodCheckEndsWith", (inst, def) => {
			$ZodCheck.init(inst, def);
			const pattern = new RegExp(`.*${escapeRegex(def.suffix)}$`);
			def.pattern ?? (def.pattern = pattern);
			inst._zod.onattach.push((inst) => {
				const bag = inst._zod.bag;
				bag.patterns ?? (bag.patterns = /* @__PURE__ */ new Set());
				bag.patterns.add(pattern);
			});
			inst._zod.check = (payload) => {
				if (payload.value.endsWith(def.suffix)) return;
				payload.issues.push({
					origin: "string",
					code: "invalid_format",
					format: "ends_with",
					suffix: def.suffix,
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodCheckOverwrite = /*@__PURE__*/ $constructor("$ZodCheckOverwrite", (inst, def) => {
			$ZodCheck.init(inst, def);
			inst._zod.check = (payload) => {
				payload.value = def.tx(payload.value);
			};
		});
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/versions.js
		const version = {
			major: 4,
			minor: 4,
			patch: 3
		};
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/schemas.js
		const $ZodType = /*@__PURE__*/ $constructor("$ZodType", (inst, def) => {
			var _a;
			inst ?? (inst = {});
			inst._zod.def = def;
			inst._zod.bag = inst._zod.bag || {};
			inst._zod.version = version;
			const checks = [...inst._zod.def.checks ?? []];
			if (inst._zod.traits.has("$ZodCheck")) checks.unshift(inst);
			for (const ch of checks) for (const fn of ch._zod.onattach) fn(inst);
			if (checks.length === 0) {
				(_a = inst._zod).deferred ?? (_a.deferred = []);
				inst._zod.deferred?.push(() => {
					inst._zod.run = inst._zod.parse;
				});
			} else {
				const runChecks = (payload, checks, ctx) => {
					let isAborted = aborted(payload);
					let asyncResult;
					for (const ch of checks) {
						if (ch._zod.def.when) {
							if (explicitlyAborted(payload)) continue;
							if (!ch._zod.def.when(payload)) continue;
						} else if (isAborted) continue;
						const currLen = payload.issues.length;
						const _ = ch._zod.check(payload);
						if (_ instanceof Promise && ctx?.async === false) throw new $ZodAsyncError();
						if (asyncResult || _ instanceof Promise) asyncResult = (asyncResult ?? Promise.resolve()).then(async () => {
							await _;
							if (payload.issues.length === currLen) return;
							if (!isAborted) isAborted = aborted(payload, currLen);
						});
						else {
							if (payload.issues.length === currLen) continue;
							if (!isAborted) isAborted = aborted(payload, currLen);
						}
					}
					if (asyncResult) return asyncResult.then(() => {
						return payload;
					});
					return payload;
				};
				const handleCanaryResult = (canary, payload, ctx) => {
					if (aborted(canary)) {
						canary.aborted = true;
						return canary;
					}
					const checkResult = runChecks(payload, checks, ctx);
					if (checkResult instanceof Promise) {
						if (ctx.async === false) throw new $ZodAsyncError();
						return checkResult.then((checkResult) => inst._zod.parse(checkResult, ctx));
					}
					return inst._zod.parse(checkResult, ctx);
				};
				inst._zod.run = (payload, ctx) => {
					if (ctx.skipChecks) return inst._zod.parse(payload, ctx);
					if (ctx.direction === "backward") {
						const canary = inst._zod.parse({
							value: payload.value,
							issues: []
						}, {
							...ctx,
							skipChecks: true
						});
						if (canary instanceof Promise) return canary.then((canary) => {
							return handleCanaryResult(canary, payload, ctx);
						});
						return handleCanaryResult(canary, payload, ctx);
					}
					const result = inst._zod.parse(payload, ctx);
					if (result instanceof Promise) {
						if (ctx.async === false) throw new $ZodAsyncError();
						return result.then((result) => runChecks(result, checks, ctx));
					}
					return runChecks(result, checks, ctx);
				};
			}
			defineLazy(inst, "~standard", () => ({
				validate: (value) => {
					try {
						const r = safeParse$1(inst, value);
						return r.success ? { value: r.data } : { issues: r.error?.issues };
					} catch (_) {
						return safeParseAsync$1(inst, value).then((r) => r.success ? { value: r.data } : { issues: r.error?.issues });
					}
				},
				vendor: "zod",
				version: 1
			}));
		});
		const $ZodString = /*@__PURE__*/ $constructor("$ZodString", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.pattern = [...inst?._zod.bag?.patterns ?? []].pop() ?? string$1(inst._zod.bag);
			inst._zod.parse = (payload, _) => {
				if (def.coerce) try {
					payload.value = String(payload.value);
				} catch (_) {}
				if (typeof payload.value === "string") return payload;
				payload.issues.push({
					expected: "string",
					code: "invalid_type",
					input: payload.value,
					inst
				});
				return payload;
			};
		});
		const $ZodStringFormat = /*@__PURE__*/ $constructor("$ZodStringFormat", (inst, def) => {
			$ZodCheckStringFormat.init(inst, def);
			$ZodString.init(inst, def);
		});
		const $ZodGUID = /*@__PURE__*/ $constructor("$ZodGUID", (inst, def) => {
			def.pattern ?? (def.pattern = guid);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodUUID = /*@__PURE__*/ $constructor("$ZodUUID", (inst, def) => {
			if (def.version) {
				const v = {
					v1: 1,
					v2: 2,
					v3: 3,
					v4: 4,
					v5: 5,
					v6: 6,
					v7: 7,
					v8: 8
				}[def.version];
				if (v === void 0) throw new Error(`Invalid UUID version: "${def.version}"`);
				def.pattern ?? (def.pattern = uuid(v));
			} else def.pattern ?? (def.pattern = uuid());
			$ZodStringFormat.init(inst, def);
		});
		const $ZodEmail = /*@__PURE__*/ $constructor("$ZodEmail", (inst, def) => {
			def.pattern ?? (def.pattern = email);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodURL = /*@__PURE__*/ $constructor("$ZodURL", (inst, def) => {
			$ZodStringFormat.init(inst, def);
			inst._zod.check = (payload) => {
				try {
					const trimmed = payload.value.trim();
					if (!def.normalize && def.protocol?.source === httpProtocol.source) {
						if (!/^https?:\/\//i.test(trimmed)) {
							payload.issues.push({
								code: "invalid_format",
								format: "url",
								note: "Invalid URL format",
								input: payload.value,
								inst,
								continue: !def.abort
							});
							return;
						}
					}
					const url = new URL(trimmed);
					if (def.hostname) {
						def.hostname.lastIndex = 0;
						if (!def.hostname.test(url.hostname)) payload.issues.push({
							code: "invalid_format",
							format: "url",
							note: "Invalid hostname",
							pattern: def.hostname.source,
							input: payload.value,
							inst,
							continue: !def.abort
						});
					}
					if (def.protocol) {
						def.protocol.lastIndex = 0;
						if (!def.protocol.test(url.protocol.endsWith(":") ? url.protocol.slice(0, -1) : url.protocol)) payload.issues.push({
							code: "invalid_format",
							format: "url",
							note: "Invalid protocol",
							pattern: def.protocol.source,
							input: payload.value,
							inst,
							continue: !def.abort
						});
					}
					if (def.normalize) payload.value = url.href;
					else payload.value = trimmed;
					return;
				} catch (_) {
					payload.issues.push({
						code: "invalid_format",
						format: "url",
						input: payload.value,
						inst,
						continue: !def.abort
					});
				}
			};
		});
		const $ZodEmoji = /*@__PURE__*/ $constructor("$ZodEmoji", (inst, def) => {
			def.pattern ?? (def.pattern = emoji());
			$ZodStringFormat.init(inst, def);
		});
		const $ZodNanoID = /*@__PURE__*/ $constructor("$ZodNanoID", (inst, def) => {
			def.pattern ?? (def.pattern = nanoid);
			$ZodStringFormat.init(inst, def);
		});
		/**
		* @deprecated CUID v1 is deprecated by its authors due to information leakage
		* (timestamps embedded in the id). Use {@link $ZodCUID2} instead.
		* See https://github.com/paralleldrive/cuid.
		*/
		const $ZodCUID = /*@__PURE__*/ $constructor("$ZodCUID", (inst, def) => {
			def.pattern ?? (def.pattern = cuid);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodCUID2 = /*@__PURE__*/ $constructor("$ZodCUID2", (inst, def) => {
			def.pattern ?? (def.pattern = cuid2);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodULID = /*@__PURE__*/ $constructor("$ZodULID", (inst, def) => {
			def.pattern ?? (def.pattern = ulid);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodXID = /*@__PURE__*/ $constructor("$ZodXID", (inst, def) => {
			def.pattern ?? (def.pattern = xid);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodKSUID = /*@__PURE__*/ $constructor("$ZodKSUID", (inst, def) => {
			def.pattern ?? (def.pattern = ksuid);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodISODateTime = /*@__PURE__*/ $constructor("$ZodISODateTime", (inst, def) => {
			def.pattern ?? (def.pattern = datetime$1(def));
			$ZodStringFormat.init(inst, def);
		});
		const $ZodISODate = /*@__PURE__*/ $constructor("$ZodISODate", (inst, def) => {
			def.pattern ?? (def.pattern = date$1);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodISOTime = /*@__PURE__*/ $constructor("$ZodISOTime", (inst, def) => {
			def.pattern ?? (def.pattern = time$1(def));
			$ZodStringFormat.init(inst, def);
		});
		const $ZodISODuration = /*@__PURE__*/ $constructor("$ZodISODuration", (inst, def) => {
			def.pattern ?? (def.pattern = duration$1);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodIPv4 = /*@__PURE__*/ $constructor("$ZodIPv4", (inst, def) => {
			def.pattern ?? (def.pattern = ipv4);
			$ZodStringFormat.init(inst, def);
			inst._zod.bag.format = `ipv4`;
		});
		const $ZodIPv6 = /*@__PURE__*/ $constructor("$ZodIPv6", (inst, def) => {
			def.pattern ?? (def.pattern = ipv6);
			$ZodStringFormat.init(inst, def);
			inst._zod.bag.format = `ipv6`;
			inst._zod.check = (payload) => {
				try {
					new URL(`http://[${payload.value}]`);
				} catch {
					payload.issues.push({
						code: "invalid_format",
						format: "ipv6",
						input: payload.value,
						inst,
						continue: !def.abort
					});
				}
			};
		});
		const $ZodCIDRv4 = /*@__PURE__*/ $constructor("$ZodCIDRv4", (inst, def) => {
			def.pattern ?? (def.pattern = cidrv4);
			$ZodStringFormat.init(inst, def);
		});
		const $ZodCIDRv6 = /*@__PURE__*/ $constructor("$ZodCIDRv6", (inst, def) => {
			def.pattern ?? (def.pattern = cidrv6);
			$ZodStringFormat.init(inst, def);
			inst._zod.check = (payload) => {
				const parts = payload.value.split("/");
				try {
					if (parts.length !== 2) throw new Error();
					const [address, prefix] = parts;
					if (!prefix) throw new Error();
					const prefixNum = Number(prefix);
					if (`${prefixNum}` !== prefix) throw new Error();
					if (prefixNum < 0 || prefixNum > 128) throw new Error();
					new URL(`http://[${address}]`);
				} catch {
					payload.issues.push({
						code: "invalid_format",
						format: "cidrv6",
						input: payload.value,
						inst,
						continue: !def.abort
					});
				}
			};
		});
		function isValidBase64(data) {
			if (data === "") return true;
			if (/\s/.test(data)) return false;
			if (data.length % 4 !== 0) return false;
			try {
				atob(data);
				return true;
			} catch {
				return false;
			}
		}
		const $ZodBase64 = /*@__PURE__*/ $constructor("$ZodBase64", (inst, def) => {
			def.pattern ?? (def.pattern = base64);
			$ZodStringFormat.init(inst, def);
			inst._zod.bag.contentEncoding = "base64";
			inst._zod.check = (payload) => {
				if (isValidBase64(payload.value)) return;
				payload.issues.push({
					code: "invalid_format",
					format: "base64",
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		function isValidBase64URL(data) {
			if (!base64url.test(data)) return false;
			const base64 = data.replace(/[-_]/g, (c) => c === "-" ? "+" : "/");
			return isValidBase64(base64.padEnd(Math.ceil(base64.length / 4) * 4, "="));
		}
		const $ZodBase64URL = /*@__PURE__*/ $constructor("$ZodBase64URL", (inst, def) => {
			def.pattern ?? (def.pattern = base64url);
			$ZodStringFormat.init(inst, def);
			inst._zod.bag.contentEncoding = "base64url";
			inst._zod.check = (payload) => {
				if (isValidBase64URL(payload.value)) return;
				payload.issues.push({
					code: "invalid_format",
					format: "base64url",
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodE164 = /*@__PURE__*/ $constructor("$ZodE164", (inst, def) => {
			def.pattern ?? (def.pattern = e164);
			$ZodStringFormat.init(inst, def);
		});
		function isValidJWT(token, algorithm = null) {
			try {
				const tokensParts = token.split(".");
				if (tokensParts.length !== 3) return false;
				const [header] = tokensParts;
				if (!header) return false;
				const parsedHeader = JSON.parse(atob(header));
				if ("typ" in parsedHeader && parsedHeader?.typ !== "JWT") return false;
				if (!parsedHeader.alg) return false;
				if (algorithm && (!("alg" in parsedHeader) || parsedHeader.alg !== algorithm)) return false;
				return true;
			} catch {
				return false;
			}
		}
		const $ZodJWT = /*@__PURE__*/ $constructor("$ZodJWT", (inst, def) => {
			$ZodStringFormat.init(inst, def);
			inst._zod.check = (payload) => {
				if (isValidJWT(payload.value, def.alg)) return;
				payload.issues.push({
					code: "invalid_format",
					format: "jwt",
					input: payload.value,
					inst,
					continue: !def.abort
				});
			};
		});
		const $ZodNumber = /*@__PURE__*/ $constructor("$ZodNumber", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.pattern = inst._zod.bag.pattern ?? number$1;
			inst._zod.parse = (payload, _ctx) => {
				if (def.coerce) try {
					payload.value = Number(payload.value);
				} catch (_) {}
				const input = payload.value;
				if (typeof input === "number" && !Number.isNaN(input) && Number.isFinite(input)) return payload;
				const received = typeof input === "number" ? Number.isNaN(input) ? "NaN" : !Number.isFinite(input) ? "Infinity" : void 0 : void 0;
				payload.issues.push({
					expected: "number",
					code: "invalid_type",
					input,
					inst,
					...received ? { received } : {}
				});
				return payload;
			};
		});
		const $ZodNumberFormat = /*@__PURE__*/ $constructor("$ZodNumberFormat", (inst, def) => {
			$ZodCheckNumberFormat.init(inst, def);
			$ZodNumber.init(inst, def);
		});
		const $ZodBoolean = /*@__PURE__*/ $constructor("$ZodBoolean", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.pattern = boolean$1;
			inst._zod.parse = (payload, _ctx) => {
				if (def.coerce) try {
					payload.value = Boolean(payload.value);
				} catch (_) {}
				const input = payload.value;
				if (typeof input === "boolean") return payload;
				payload.issues.push({
					expected: "boolean",
					code: "invalid_type",
					input,
					inst
				});
				return payload;
			};
		});
		const $ZodNull = /*@__PURE__*/ $constructor("$ZodNull", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.pattern = _null$2;
			inst._zod.values = new Set([null]);
			inst._zod.parse = (payload, _ctx) => {
				const input = payload.value;
				if (input === null) return payload;
				payload.issues.push({
					expected: "null",
					code: "invalid_type",
					input,
					inst
				});
				return payload;
			};
		});
		function handleArrayResult(result, final, index) {
			if (result.issues.length) final.issues.push(...prefixIssues(index, result.issues));
			final.value[index] = result.value;
		}
		const $ZodArray = /*@__PURE__*/ $constructor("$ZodArray", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.parse = (payload, ctx) => {
				const input = payload.value;
				if (!Array.isArray(input)) {
					payload.issues.push({
						expected: "array",
						code: "invalid_type",
						input,
						inst
					});
					return payload;
				}
				payload.value = Array(input.length);
				const proms = [];
				for (let i = 0; i < input.length; i++) {
					const item = input[i];
					const result = def.element._zod.run({
						value: item,
						issues: []
					}, ctx);
					if (result instanceof Promise) proms.push(result.then((result) => handleArrayResult(result, payload, i)));
					else handleArrayResult(result, payload, i);
				}
				if (proms.length) return Promise.all(proms).then(() => payload);
				return payload;
			};
		});
		function handleUnionResults(results, final, inst, ctx) {
			for (const result of results) if (result.issues.length === 0) {
				final.value = result.value;
				return final;
			}
			const nonaborted = results.filter((r) => !aborted(r));
			if (nonaborted.length === 1) {
				final.value = nonaborted[0].value;
				return nonaborted[0];
			}
			final.issues.push({
				code: "invalid_union",
				input: final.value,
				inst,
				errors: results.map((result) => result.issues.map((iss) => finalizeIssue(iss, ctx, config())))
			});
			return final;
		}
		const $ZodUnion = /*@__PURE__*/ $constructor("$ZodUnion", (inst, def) => {
			$ZodType.init(inst, def);
			defineLazy(inst._zod, "optin", () => def.options.some((o) => o._zod.optin === "optional") ? "optional" : void 0);
			defineLazy(inst._zod, "optout", () => def.options.some((o) => o._zod.optout === "optional") ? "optional" : void 0);
			defineLazy(inst._zod, "values", () => {
				if (def.options.every((o) => o._zod.values)) return new Set(def.options.flatMap((option) => Array.from(option._zod.values)));
			});
			defineLazy(inst._zod, "pattern", () => {
				if (def.options.every((o) => o._zod.pattern)) {
					const patterns = def.options.map((o) => o._zod.pattern);
					return new RegExp(`^(${patterns.map((p) => cleanRegex(p.source)).join("|")})$`);
				}
			});
			const first = def.options.length === 1 ? def.options[0]._zod.run : null;
			inst._zod.parse = (payload, ctx) => {
				if (first) return first(payload, ctx);
				let async = false;
				const results = [];
				for (const option of def.options) {
					const result = option._zod.run({
						value: payload.value,
						issues: []
					}, ctx);
					if (result instanceof Promise) {
						results.push(result);
						async = true;
					} else {
						if (result.issues.length === 0) return result;
						results.push(result);
					}
				}
				if (!async) return handleUnionResults(results, payload, inst, ctx);
				return Promise.all(results).then((results) => {
					return handleUnionResults(results, payload, inst, ctx);
				});
			};
		});
		const $ZodIntersection = /*@__PURE__*/ $constructor("$ZodIntersection", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.parse = (payload, ctx) => {
				const input = payload.value;
				const left = def.left._zod.run({
					value: input,
					issues: []
				}, ctx);
				const right = def.right._zod.run({
					value: input,
					issues: []
				}, ctx);
				if (left instanceof Promise || right instanceof Promise) return Promise.all([left, right]).then(([left, right]) => {
					return handleIntersectionResults(payload, left, right);
				});
				return handleIntersectionResults(payload, left, right);
			};
		});
		function mergeValues(a, b) {
			if (a === b) return {
				valid: true,
				data: a
			};
			if (a instanceof Date && b instanceof Date && +a === +b) return {
				valid: true,
				data: a
			};
			if (isPlainObject(a) && isPlainObject(b)) {
				const bKeys = Object.keys(b);
				const sharedKeys = Object.keys(a).filter((key) => bKeys.indexOf(key) !== -1);
				const newObj = {
					...a,
					...b
				};
				for (const key of sharedKeys) {
					const sharedValue = mergeValues(a[key], b[key]);
					if (!sharedValue.valid) return {
						valid: false,
						mergeErrorPath: [key, ...sharedValue.mergeErrorPath]
					};
					newObj[key] = sharedValue.data;
				}
				return {
					valid: true,
					data: newObj
				};
			}
			if (Array.isArray(a) && Array.isArray(b)) {
				if (a.length !== b.length) return {
					valid: false,
					mergeErrorPath: []
				};
				const newArray = [];
				for (let index = 0; index < a.length; index++) {
					const itemA = a[index];
					const itemB = b[index];
					const sharedValue = mergeValues(itemA, itemB);
					if (!sharedValue.valid) return {
						valid: false,
						mergeErrorPath: [index, ...sharedValue.mergeErrorPath]
					};
					newArray.push(sharedValue.data);
				}
				return {
					valid: true,
					data: newArray
				};
			}
			return {
				valid: false,
				mergeErrorPath: []
			};
		}
		function handleIntersectionResults(result, left, right) {
			const unrecKeys = /* @__PURE__ */ new Map();
			let unrecIssue;
			for (const iss of left.issues) if (iss.code === "unrecognized_keys") {
				unrecIssue ?? (unrecIssue = iss);
				for (const k of iss.keys) {
					if (!unrecKeys.has(k)) unrecKeys.set(k, {});
					unrecKeys.get(k).l = true;
				}
			} else result.issues.push(iss);
			for (const iss of right.issues) if (iss.code === "unrecognized_keys") for (const k of iss.keys) {
				if (!unrecKeys.has(k)) unrecKeys.set(k, {});
				unrecKeys.get(k).r = true;
			}
			else result.issues.push(iss);
			const bothKeys = [...unrecKeys].filter(([, f]) => f.l && f.r).map(([k]) => k);
			if (bothKeys.length && unrecIssue) result.issues.push({
				...unrecIssue,
				keys: bothKeys
			});
			if (aborted(result)) return result;
			const merged = mergeValues(left.value, right.value);
			if (!merged.valid) throw new Error(`Unmergable intersection. Error path: ${JSON.stringify(merged.mergeErrorPath)}`);
			result.value = merged.data;
			return result;
		}
		const $ZodRecord = /*@__PURE__*/ $constructor("$ZodRecord", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.parse = (payload, ctx) => {
				const input = payload.value;
				if (!isPlainObject(input)) {
					payload.issues.push({
						expected: "record",
						code: "invalid_type",
						input,
						inst
					});
					return payload;
				}
				const proms = [];
				const values = def.keyType._zod.values;
				if (values) {
					payload.value = {};
					const recordKeys = /* @__PURE__ */ new Set();
					for (const key of values) if (typeof key === "string" || typeof key === "number" || typeof key === "symbol") {
						recordKeys.add(typeof key === "number" ? key.toString() : key);
						const keyResult = def.keyType._zod.run({
							value: key,
							issues: []
						}, ctx);
						if (keyResult instanceof Promise) throw new Error("Async schemas not supported in object keys currently");
						if (keyResult.issues.length) {
							payload.issues.push({
								code: "invalid_key",
								origin: "record",
								issues: keyResult.issues.map((iss) => finalizeIssue(iss, ctx, config())),
								input: key,
								path: [key],
								inst
							});
							continue;
						}
						const outKey = keyResult.value;
						const result = def.valueType._zod.run({
							value: input[key],
							issues: []
						}, ctx);
						if (result instanceof Promise) proms.push(result.then((result) => {
							if (result.issues.length) payload.issues.push(...prefixIssues(key, result.issues));
							payload.value[outKey] = result.value;
						}));
						else {
							if (result.issues.length) payload.issues.push(...prefixIssues(key, result.issues));
							payload.value[outKey] = result.value;
						}
					}
					let unrecognized;
					for (const key in input) if (!recordKeys.has(key)) {
						unrecognized = unrecognized ?? [];
						unrecognized.push(key);
					}
					if (unrecognized && unrecognized.length > 0) payload.issues.push({
						code: "unrecognized_keys",
						input,
						inst,
						keys: unrecognized
					});
				} else {
					payload.value = {};
					for (const key of Reflect.ownKeys(input)) {
						if (key === "__proto__") continue;
						if (!Object.prototype.propertyIsEnumerable.call(input, key)) continue;
						let keyResult = def.keyType._zod.run({
							value: key,
							issues: []
						}, ctx);
						if (keyResult instanceof Promise) throw new Error("Async schemas not supported in object keys currently");
						if (typeof key === "string" && number$1.test(key) && keyResult.issues.length) {
							const retryResult = def.keyType._zod.run({
								value: Number(key),
								issues: []
							}, ctx);
							if (retryResult instanceof Promise) throw new Error("Async schemas not supported in object keys currently");
							if (retryResult.issues.length === 0) keyResult = retryResult;
						}
						if (keyResult.issues.length) {
							if (def.mode === "loose") payload.value[key] = input[key];
							else payload.issues.push({
								code: "invalid_key",
								origin: "record",
								issues: keyResult.issues.map((iss) => finalizeIssue(iss, ctx, config())),
								input: key,
								path: [key],
								inst
							});
							continue;
						}
						const result = def.valueType._zod.run({
							value: input[key],
							issues: []
						}, ctx);
						if (result instanceof Promise) proms.push(result.then((result) => {
							if (result.issues.length) payload.issues.push(...prefixIssues(key, result.issues));
							payload.value[keyResult.value] = result.value;
						}));
						else {
							if (result.issues.length) payload.issues.push(...prefixIssues(key, result.issues));
							payload.value[keyResult.value] = result.value;
						}
					}
				}
				if (proms.length) return Promise.all(proms).then(() => payload);
				return payload;
			};
		});
		const $ZodTransform = /*@__PURE__*/ $constructor("$ZodTransform", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.optin = "optional";
			inst._zod.parse = (payload, ctx) => {
				if (ctx.direction === "backward") throw new $ZodEncodeError(inst.constructor.name);
				const _out = def.transform(payload.value, payload);
				if (ctx.async) return (_out instanceof Promise ? _out : Promise.resolve(_out)).then((output) => {
					payload.value = output;
					payload.fallback = true;
					return payload;
				});
				if (_out instanceof Promise) throw new $ZodAsyncError();
				payload.value = _out;
				payload.fallback = true;
				return payload;
			};
		});
		function handleOptionalResult(result, input) {
			if (input === void 0 && (result.issues.length || result.fallback)) return {
				issues: [],
				value: void 0
			};
			return result;
		}
		const $ZodOptional = /*@__PURE__*/ $constructor("$ZodOptional", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.optin = "optional";
			inst._zod.optout = "optional";
			defineLazy(inst._zod, "values", () => {
				return def.innerType._zod.values ? new Set([...def.innerType._zod.values, void 0]) : void 0;
			});
			defineLazy(inst._zod, "pattern", () => {
				const pattern = def.innerType._zod.pattern;
				return pattern ? new RegExp(`^(${cleanRegex(pattern.source)})?$`) : void 0;
			});
			inst._zod.parse = (payload, ctx) => {
				if (def.innerType._zod.optin === "optional") {
					const input = payload.value;
					const result = def.innerType._zod.run(payload, ctx);
					if (result instanceof Promise) return result.then((r) => handleOptionalResult(r, input));
					return handleOptionalResult(result, input);
				}
				if (payload.value === void 0) return payload;
				return def.innerType._zod.run(payload, ctx);
			};
		});
		const $ZodExactOptional = /*@__PURE__*/ $constructor("$ZodExactOptional", (inst, def) => {
			$ZodOptional.init(inst, def);
			defineLazy(inst._zod, "values", () => def.innerType._zod.values);
			defineLazy(inst._zod, "pattern", () => def.innerType._zod.pattern);
			inst._zod.parse = (payload, ctx) => {
				return def.innerType._zod.run(payload, ctx);
			};
		});
		const $ZodNullable = /*@__PURE__*/ $constructor("$ZodNullable", (inst, def) => {
			$ZodType.init(inst, def);
			defineLazy(inst._zod, "optin", () => def.innerType._zod.optin);
			defineLazy(inst._zod, "optout", () => def.innerType._zod.optout);
			defineLazy(inst._zod, "pattern", () => {
				const pattern = def.innerType._zod.pattern;
				return pattern ? new RegExp(`^(${cleanRegex(pattern.source)}|null)$`) : void 0;
			});
			defineLazy(inst._zod, "values", () => {
				return def.innerType._zod.values ? new Set([...def.innerType._zod.values, null]) : void 0;
			});
			inst._zod.parse = (payload, ctx) => {
				if (payload.value === null) return payload;
				return def.innerType._zod.run(payload, ctx);
			};
		});
		const $ZodDefault = /*@__PURE__*/ $constructor("$ZodDefault", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.optin = "optional";
			defineLazy(inst._zod, "values", () => def.innerType._zod.values);
			inst._zod.parse = (payload, ctx) => {
				if (ctx.direction === "backward") return def.innerType._zod.run(payload, ctx);
				if (payload.value === void 0) {
					payload.value = def.defaultValue;
					/**
					* $ZodDefault returns the default value immediately in forward direction.
					* It doesn't pass the default value into the validator ("prefault"). There's no reason to pass the default value through validation. The validity of the default is enforced by TypeScript statically. Otherwise, it's the responsibility of the user to ensure the default is valid. In the case of pipes with divergent in/out types, you can specify the default on the `in` schema of your ZodPipe to set a "prefault" for the pipe.   */
					return payload;
				}
				const result = def.innerType._zod.run(payload, ctx);
				if (result instanceof Promise) return result.then((result) => handleDefaultResult(result, def));
				return handleDefaultResult(result, def);
			};
		});
		function handleDefaultResult(payload, def) {
			if (payload.value === void 0) payload.value = def.defaultValue;
			return payload;
		}
		const $ZodPrefault = /*@__PURE__*/ $constructor("$ZodPrefault", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.optin = "optional";
			defineLazy(inst._zod, "values", () => def.innerType._zod.values);
			inst._zod.parse = (payload, ctx) => {
				if (ctx.direction === "backward") return def.innerType._zod.run(payload, ctx);
				if (payload.value === void 0) payload.value = def.defaultValue;
				return def.innerType._zod.run(payload, ctx);
			};
		});
		const $ZodNonOptional = /*@__PURE__*/ $constructor("$ZodNonOptional", (inst, def) => {
			$ZodType.init(inst, def);
			defineLazy(inst._zod, "values", () => {
				const v = def.innerType._zod.values;
				return v ? new Set([...v].filter((x) => x !== void 0)) : void 0;
			});
			inst._zod.parse = (payload, ctx) => {
				const result = def.innerType._zod.run(payload, ctx);
				if (result instanceof Promise) return result.then((result) => handleNonOptionalResult(result, inst));
				return handleNonOptionalResult(result, inst);
			};
		});
		function handleNonOptionalResult(payload, inst) {
			if (!payload.issues.length && payload.value === void 0) payload.issues.push({
				code: "invalid_type",
				expected: "nonoptional",
				input: payload.value,
				inst
			});
			return payload;
		}
		const $ZodCatch = /*@__PURE__*/ $constructor("$ZodCatch", (inst, def) => {
			$ZodType.init(inst, def);
			inst._zod.optin = "optional";
			defineLazy(inst._zod, "optout", () => def.innerType._zod.optout);
			defineLazy(inst._zod, "values", () => def.innerType._zod.values);
			inst._zod.parse = (payload, ctx) => {
				if (ctx.direction === "backward") return def.innerType._zod.run(payload, ctx);
				const result = def.innerType._zod.run(payload, ctx);
				if (result instanceof Promise) return result.then((result) => {
					payload.value = result.value;
					if (result.issues.length) {
						payload.value = def.catchValue({
							...payload,
							error: { issues: result.issues.map((iss) => finalizeIssue(iss, ctx, config())) },
							input: payload.value
						});
						payload.issues = [];
						payload.fallback = true;
					}
					return payload;
				});
				payload.value = result.value;
				if (result.issues.length) {
					payload.value = def.catchValue({
						...payload,
						error: { issues: result.issues.map((iss) => finalizeIssue(iss, ctx, config())) },
						input: payload.value
					});
					payload.issues = [];
					payload.fallback = true;
				}
				return payload;
			};
		});
		const $ZodPipe = /*@__PURE__*/ $constructor("$ZodPipe", (inst, def) => {
			$ZodType.init(inst, def);
			defineLazy(inst._zod, "values", () => def.in._zod.values);
			defineLazy(inst._zod, "optin", () => def.in._zod.optin);
			defineLazy(inst._zod, "optout", () => def.out._zod.optout);
			defineLazy(inst._zod, "propValues", () => def.in._zod.propValues);
			inst._zod.parse = (payload, ctx) => {
				if (ctx.direction === "backward") {
					const right = def.out._zod.run(payload, ctx);
					if (right instanceof Promise) return right.then((right) => handlePipeResult(right, def.in, ctx));
					return handlePipeResult(right, def.in, ctx);
				}
				const left = def.in._zod.run(payload, ctx);
				if (left instanceof Promise) return left.then((left) => handlePipeResult(left, def.out, ctx));
				return handlePipeResult(left, def.out, ctx);
			};
		});
		function handlePipeResult(left, next, ctx) {
			if (left.issues.length) {
				left.aborted = true;
				return left;
			}
			return next._zod.run({
				value: left.value,
				issues: left.issues,
				fallback: left.fallback
			}, ctx);
		}
		const $ZodReadonly = /*@__PURE__*/ $constructor("$ZodReadonly", (inst, def) => {
			$ZodType.init(inst, def);
			defineLazy(inst._zod, "propValues", () => def.innerType._zod.propValues);
			defineLazy(inst._zod, "values", () => def.innerType._zod.values);
			defineLazy(inst._zod, "optin", () => def.innerType?._zod?.optin);
			defineLazy(inst._zod, "optout", () => def.innerType?._zod?.optout);
			inst._zod.parse = (payload, ctx) => {
				if (ctx.direction === "backward") return def.innerType._zod.run(payload, ctx);
				const result = def.innerType._zod.run(payload, ctx);
				if (result instanceof Promise) return result.then(handleReadonlyResult);
				return handleReadonlyResult(result);
			};
		});
		function handleReadonlyResult(payload) {
			payload.value = Object.freeze(payload.value);
			return payload;
		}
		const $ZodLazy = /*@__PURE__*/ $constructor("$ZodLazy", (inst, def) => {
			$ZodType.init(inst, def);
			defineLazy(inst._zod, "innerType", () => {
				const d = def;
				if (!d._cachedInner) d._cachedInner = def.getter();
				return d._cachedInner;
			});
			defineLazy(inst._zod, "pattern", () => inst._zod.innerType?._zod?.pattern);
			defineLazy(inst._zod, "propValues", () => inst._zod.innerType?._zod?.propValues);
			defineLazy(inst._zod, "optin", () => inst._zod.innerType?._zod?.optin ?? void 0);
			defineLazy(inst._zod, "optout", () => inst._zod.innerType?._zod?.optout ?? void 0);
			inst._zod.parse = (payload, ctx) => {
				return inst._zod.innerType._zod.run(payload, ctx);
			};
		});
		const $ZodCustom = /*@__PURE__*/ $constructor("$ZodCustom", (inst, def) => {
			$ZodCheck.init(inst, def);
			$ZodType.init(inst, def);
			inst._zod.parse = (payload, _) => {
				return payload;
			};
			inst._zod.check = (payload) => {
				const input = payload.value;
				const r = def.fn(input);
				if (r instanceof Promise) return r.then((r) => handleRefineResult(r, payload, input, inst));
				handleRefineResult(r, payload, input, inst);
			};
		});
		function handleRefineResult(result, payload, input, inst) {
			if (!result) {
				const _iss = {
					code: "custom",
					input,
					inst,
					path: [...inst._zod.def.path ?? []],
					continue: !inst._zod.def.abort
				};
				if (inst._zod.def.params) _iss.params = inst._zod.def.params;
				payload.issues.push(issue(_iss));
			}
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/registries.js
		var _a;
		var $ZodRegistry = class {
			constructor() {
				this._map = /* @__PURE__ */ new WeakMap();
				this._idmap = /* @__PURE__ */ new Map();
			}
			add(schema, ..._meta) {
				const meta = _meta[0];
				this._map.set(schema, meta);
				if (meta && typeof meta === "object" && "id" in meta) this._idmap.set(meta.id, schema);
				return this;
			}
			clear() {
				this._map = /* @__PURE__ */ new WeakMap();
				this._idmap = /* @__PURE__ */ new Map();
				return this;
			}
			remove(schema) {
				const meta = this._map.get(schema);
				if (meta && typeof meta === "object" && "id" in meta) this._idmap.delete(meta.id);
				this._map.delete(schema);
				return this;
			}
			get(schema) {
				const p = schema._zod.parent;
				if (p) {
					const pm = { ...this.get(p) ?? {} };
					delete pm.id;
					const f = {
						...pm,
						...this._map.get(schema)
					};
					return Object.keys(f).length ? f : void 0;
				}
				return this._map.get(schema);
			}
			has(schema) {
				return this._map.has(schema);
			}
		};
		function registry() {
			return new $ZodRegistry();
		}
		(_a = globalThis).__zod_globalRegistry ?? (_a.__zod_globalRegistry = registry());
		const globalRegistry = globalThis.__zod_globalRegistry;
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/api.js
		// @__NO_SIDE_EFFECTS__
		function _string(Class, params) {
			return new Class({
				type: "string",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _email(Class, params) {
			return new Class({
				type: "string",
				format: "email",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _guid(Class, params) {
			return new Class({
				type: "string",
				format: "guid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _uuid(Class, params) {
			return new Class({
				type: "string",
				format: "uuid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _uuidv4(Class, params) {
			return new Class({
				type: "string",
				format: "uuid",
				check: "string_format",
				abort: false,
				version: "v4",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _uuidv6(Class, params) {
			return new Class({
				type: "string",
				format: "uuid",
				check: "string_format",
				abort: false,
				version: "v6",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _uuidv7(Class, params) {
			return new Class({
				type: "string",
				format: "uuid",
				check: "string_format",
				abort: false,
				version: "v7",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _url(Class, params) {
			return new Class({
				type: "string",
				format: "url",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _emoji(Class, params) {
			return new Class({
				type: "string",
				format: "emoji",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _nanoid(Class, params) {
			return new Class({
				type: "string",
				format: "nanoid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		/**
		* @deprecated CUID v1 is deprecated by its authors due to information leakage
		* (timestamps embedded in the id). Use {@link _cuid2} instead.
		* See https://github.com/paralleldrive/cuid.
		*/
		// @__NO_SIDE_EFFECTS__
		function _cuid(Class, params) {
			return new Class({
				type: "string",
				format: "cuid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _cuid2(Class, params) {
			return new Class({
				type: "string",
				format: "cuid2",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _ulid(Class, params) {
			return new Class({
				type: "string",
				format: "ulid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _xid(Class, params) {
			return new Class({
				type: "string",
				format: "xid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _ksuid(Class, params) {
			return new Class({
				type: "string",
				format: "ksuid",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _ipv4(Class, params) {
			return new Class({
				type: "string",
				format: "ipv4",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _ipv6(Class, params) {
			return new Class({
				type: "string",
				format: "ipv6",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _cidrv4(Class, params) {
			return new Class({
				type: "string",
				format: "cidrv4",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _cidrv6(Class, params) {
			return new Class({
				type: "string",
				format: "cidrv6",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _base64(Class, params) {
			return new Class({
				type: "string",
				format: "base64",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _base64url(Class, params) {
			return new Class({
				type: "string",
				format: "base64url",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _e164(Class, params) {
			return new Class({
				type: "string",
				format: "e164",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _jwt(Class, params) {
			return new Class({
				type: "string",
				format: "jwt",
				check: "string_format",
				abort: false,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _isoDateTime(Class, params) {
			return new Class({
				type: "string",
				format: "datetime",
				check: "string_format",
				offset: false,
				local: false,
				precision: null,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _isoDate(Class, params) {
			return new Class({
				type: "string",
				format: "date",
				check: "string_format",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _isoTime(Class, params) {
			return new Class({
				type: "string",
				format: "time",
				check: "string_format",
				precision: null,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _isoDuration(Class, params) {
			return new Class({
				type: "string",
				format: "duration",
				check: "string_format",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _number(Class, params) {
			return new Class({
				type: "number",
				checks: [],
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _int(Class, params) {
			return new Class({
				type: "number",
				check: "number_format",
				abort: false,
				format: "safeint",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _boolean(Class, params) {
			return new Class({
				type: "boolean",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _null$1(Class, params) {
			return new Class({
				type: "null",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _lt(value, params) {
			return new $ZodCheckLessThan({
				check: "less_than",
				...normalizeParams(params),
				value,
				inclusive: false
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _lte(value, params) {
			return new $ZodCheckLessThan({
				check: "less_than",
				...normalizeParams(params),
				value,
				inclusive: true
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _gt(value, params) {
			return new $ZodCheckGreaterThan({
				check: "greater_than",
				...normalizeParams(params),
				value,
				inclusive: false
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _gte(value, params) {
			return new $ZodCheckGreaterThan({
				check: "greater_than",
				...normalizeParams(params),
				value,
				inclusive: true
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _multipleOf(value, params) {
			return new $ZodCheckMultipleOf({
				check: "multiple_of",
				...normalizeParams(params),
				value
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _maxLength(maximum, params) {
			return new $ZodCheckMaxLength({
				check: "max_length",
				...normalizeParams(params),
				maximum
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _minLength(minimum, params) {
			return new $ZodCheckMinLength({
				check: "min_length",
				...normalizeParams(params),
				minimum
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _length(length, params) {
			return new $ZodCheckLengthEquals({
				check: "length_equals",
				...normalizeParams(params),
				length
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _regex(pattern, params) {
			return new $ZodCheckRegex({
				check: "string_format",
				format: "regex",
				...normalizeParams(params),
				pattern
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _lowercase(params) {
			return new $ZodCheckLowerCase({
				check: "string_format",
				format: "lowercase",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _uppercase(params) {
			return new $ZodCheckUpperCase({
				check: "string_format",
				format: "uppercase",
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _includes(includes, params) {
			return new $ZodCheckIncludes({
				check: "string_format",
				format: "includes",
				...normalizeParams(params),
				includes
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _startsWith(prefix, params) {
			return new $ZodCheckStartsWith({
				check: "string_format",
				format: "starts_with",
				...normalizeParams(params),
				prefix
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _endsWith(suffix, params) {
			return new $ZodCheckEndsWith({
				check: "string_format",
				format: "ends_with",
				...normalizeParams(params),
				suffix
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _overwrite(tx) {
			return new $ZodCheckOverwrite({
				check: "overwrite",
				tx
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _normalize(form) {
			return /* @__PURE__ */ _overwrite((input) => input.normalize(form));
		}
		// @__NO_SIDE_EFFECTS__
		function _trim() {
			return /* @__PURE__ */ _overwrite((input) => input.trim());
		}
		// @__NO_SIDE_EFFECTS__
		function _toLowerCase() {
			return /* @__PURE__ */ _overwrite((input) => input.toLowerCase());
		}
		// @__NO_SIDE_EFFECTS__
		function _toUpperCase() {
			return /* @__PURE__ */ _overwrite((input) => input.toUpperCase());
		}
		// @__NO_SIDE_EFFECTS__
		function _slugify() {
			return /* @__PURE__ */ _overwrite((input) => slugify(input));
		}
		// @__NO_SIDE_EFFECTS__
		function _array(Class, element, params) {
			return new Class({
				type: "array",
				element,
				...normalizeParams(params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _refine(Class, fn, _params) {
			return new Class({
				type: "custom",
				check: "custom",
				fn,
				...normalizeParams(_params)
			});
		}
		// @__NO_SIDE_EFFECTS__
		function _superRefine(fn, params) {
			const ch = /* @__PURE__ */ _check((payload) => {
				payload.addIssue = (issue$2) => {
					if (typeof issue$2 === "string") payload.issues.push(issue(issue$2, payload.value, ch._zod.def));
					else {
						const _issue = issue$2;
						if (_issue.fatal) _issue.continue = false;
						_issue.code ?? (_issue.code = "custom");
						_issue.input ?? (_issue.input = payload.value);
						_issue.inst ?? (_issue.inst = ch);
						_issue.continue ?? (_issue.continue = !ch._zod.def.abort);
						payload.issues.push(issue(_issue));
					}
				};
				return fn(payload.value, payload);
			}, params);
			return ch;
		}
		// @__NO_SIDE_EFFECTS__
		function _check(fn, params) {
			const ch = new $ZodCheck({
				check: "custom",
				...normalizeParams(params)
			});
			ch._zod.check = fn;
			return ch;
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/to-json-schema.js
		function initializeContext(params) {
			let target = params?.target ?? "draft-2020-12";
			if (target === "draft-4") target = "draft-04";
			if (target === "draft-7") target = "draft-07";
			return {
				processors: params.processors ?? {},
				metadataRegistry: params?.metadata ?? globalRegistry,
				target,
				unrepresentable: params?.unrepresentable ?? "throw",
				override: params?.override ?? (() => {}),
				io: params?.io ?? "output",
				counter: 0,
				seen: /* @__PURE__ */ new Map(),
				cycles: params?.cycles ?? "ref",
				reused: params?.reused ?? "inline",
				external: params?.external ?? void 0
			};
		}
		function process(schema, ctx, _params = {
			path: [],
			schemaPath: []
		}) {
			var _a;
			const def = schema._zod.def;
			const seen = ctx.seen.get(schema);
			if (seen) {
				seen.count++;
				if (_params.schemaPath.includes(schema)) seen.cycle = _params.path;
				return seen.schema;
			}
			const result = {
				schema: {},
				count: 1,
				cycle: void 0,
				path: _params.path
			};
			ctx.seen.set(schema, result);
			const overrideSchema = schema._zod.toJSONSchema?.();
			if (overrideSchema) result.schema = overrideSchema;
			else {
				const params = {
					..._params,
					schemaPath: [..._params.schemaPath, schema],
					path: _params.path
				};
				if (schema._zod.processJSONSchema) schema._zod.processJSONSchema(ctx, result.schema, params);
				else {
					const _json = result.schema;
					const processor = ctx.processors[def.type];
					if (!processor) throw new Error(`[toJSONSchema]: Non-representable type encountered: ${def.type}`);
					processor(schema, ctx, _json, params);
				}
				const parent = schema._zod.parent;
				if (parent) {
					if (!result.ref) result.ref = parent;
					process(parent, ctx, params);
					ctx.seen.get(parent).isParent = true;
				}
			}
			const meta = ctx.metadataRegistry.get(schema);
			if (meta) Object.assign(result.schema, meta);
			if (ctx.io === "input" && isTransforming(schema)) {
				delete result.schema.examples;
				delete result.schema.default;
			}
			if (ctx.io === "input" && "_prefault" in result.schema) (_a = result.schema).default ?? (_a.default = result.schema._prefault);
			delete result.schema._prefault;
			return ctx.seen.get(schema).schema;
		}
		function extractDefs(ctx, schema) {
			const root = ctx.seen.get(schema);
			if (!root) throw new Error("Unprocessed schema. This is a bug in Zod.");
			const idToSchema = /* @__PURE__ */ new Map();
			for (const entry of ctx.seen.entries()) {
				const id = ctx.metadataRegistry.get(entry[0])?.id;
				if (id) {
					const existing = idToSchema.get(id);
					if (existing && existing !== entry[0]) throw new Error(`Duplicate schema id "${id}" detected during JSON Schema conversion. Two different schemas cannot share the same id when converted together.`);
					idToSchema.set(id, entry[0]);
				}
			}
			const makeURI = (entry) => {
				const defsSegment = ctx.target === "draft-2020-12" ? "$defs" : "definitions";
				if (ctx.external) {
					const externalId = ctx.external.registry.get(entry[0])?.id;
					const uriGenerator = ctx.external.uri ?? ((id) => id);
					if (externalId) return { ref: uriGenerator(externalId) };
					const id = entry[1].defId ?? entry[1].schema.id ?? `schema${ctx.counter++}`;
					entry[1].defId = id;
					return {
						defId: id,
						ref: `${uriGenerator("__shared")}#/${defsSegment}/${id}`
					};
				}
				if (entry[1] === root) return { ref: "#" };
				const defUriPrefix = `#/${defsSegment}/`;
				const defId = entry[1].schema.id ?? `__schema${ctx.counter++}`;
				return {
					defId,
					ref: defUriPrefix + defId
				};
			};
			const extractToDef = (entry) => {
				if (entry[1].schema.$ref) return;
				const seen = entry[1];
				const { ref, defId } = makeURI(entry);
				seen.def = { ...seen.schema };
				if (defId) seen.defId = defId;
				const schema = seen.schema;
				for (const key in schema) delete schema[key];
				schema.$ref = ref;
			};
			if (ctx.cycles === "throw") for (const entry of ctx.seen.entries()) {
				const seen = entry[1];
				if (seen.cycle) throw new Error(`Cycle detected: #/${seen.cycle?.join("/")}/<root>

Set the \`cycles\` parameter to \`"ref"\` to resolve cyclical schemas with defs.`);
			}
			for (const entry of ctx.seen.entries()) {
				const seen = entry[1];
				if (schema === entry[0]) {
					extractToDef(entry);
					continue;
				}
				if (ctx.external) {
					const ext = ctx.external.registry.get(entry[0])?.id;
					if (schema !== entry[0] && ext) {
						extractToDef(entry);
						continue;
					}
				}
				if (ctx.metadataRegistry.get(entry[0])?.id) {
					extractToDef(entry);
					continue;
				}
				if (seen.cycle) {
					extractToDef(entry);
					continue;
				}
				if (seen.count > 1) {
					if (ctx.reused === "ref") {
						extractToDef(entry);
						continue;
					}
				}
			}
		}
		function finalize(ctx, schema) {
			const root = ctx.seen.get(schema);
			if (!root) throw new Error("Unprocessed schema. This is a bug in Zod.");
			const flattenRef = (zodSchema) => {
				const seen = ctx.seen.get(zodSchema);
				if (seen.ref === null) return;
				const schema = seen.def ?? seen.schema;
				const _cached = { ...schema };
				const ref = seen.ref;
				seen.ref = null;
				if (ref) {
					flattenRef(ref);
					const refSeen = ctx.seen.get(ref);
					const refSchema = refSeen.schema;
					if (refSchema.$ref && (ctx.target === "draft-07" || ctx.target === "draft-04" || ctx.target === "openapi-3.0")) {
						schema.allOf = schema.allOf ?? [];
						schema.allOf.push(refSchema);
					} else Object.assign(schema, refSchema);
					Object.assign(schema, _cached);
					if (zodSchema._zod.parent === ref) for (const key in schema) {
						if (key === "$ref" || key === "allOf") continue;
						if (!(key in _cached)) delete schema[key];
					}
					if (refSchema.$ref && refSeen.def) for (const key in schema) {
						if (key === "$ref" || key === "allOf") continue;
						if (key in refSeen.def && JSON.stringify(schema[key]) === JSON.stringify(refSeen.def[key])) delete schema[key];
					}
				}
				const parent = zodSchema._zod.parent;
				if (parent && parent !== ref) {
					flattenRef(parent);
					const parentSeen = ctx.seen.get(parent);
					if (parentSeen?.schema.$ref) {
						schema.$ref = parentSeen.schema.$ref;
						if (parentSeen.def) for (const key in schema) {
							if (key === "$ref" || key === "allOf") continue;
							if (key in parentSeen.def && JSON.stringify(schema[key]) === JSON.stringify(parentSeen.def[key])) delete schema[key];
						}
					}
				}
				ctx.override({
					zodSchema,
					jsonSchema: schema,
					path: seen.path ?? []
				});
			};
			for (const entry of [...ctx.seen.entries()].reverse()) flattenRef(entry[0]);
			const result = {};
			if (ctx.target === "draft-2020-12") result.$schema = "https://json-schema.org/draft/2020-12/schema";
			else if (ctx.target === "draft-07") result.$schema = "http://json-schema.org/draft-07/schema#";
			else if (ctx.target === "draft-04") result.$schema = "http://json-schema.org/draft-04/schema#";
			else if (ctx.target === "openapi-3.0") {}
			if (ctx.external?.uri) {
				const id = ctx.external.registry.get(schema)?.id;
				if (!id) throw new Error("Schema is missing an `id` property");
				result.$id = ctx.external.uri(id);
			}
			Object.assign(result, root.def ?? root.schema);
			const rootMetaId = ctx.metadataRegistry.get(schema)?.id;
			if (rootMetaId !== void 0 && result.id === rootMetaId) delete result.id;
			const defs = ctx.external?.defs ?? {};
			for (const entry of ctx.seen.entries()) {
				const seen = entry[1];
				if (seen.def && seen.defId) {
					if (seen.def.id === seen.defId) delete seen.def.id;
					defs[seen.defId] = seen.def;
				}
			}
			if (ctx.external) {} else if (Object.keys(defs).length > 0) if (ctx.target === "draft-2020-12") result.$defs = defs;
			else result.definitions = defs;
			try {
				const finalized = JSON.parse(JSON.stringify(result));
				Object.defineProperty(finalized, "~standard", {
					value: {
						...schema["~standard"],
						jsonSchema: {
							input: createStandardJSONSchemaMethod(schema, "input", ctx.processors),
							output: createStandardJSONSchemaMethod(schema, "output", ctx.processors)
						}
					},
					enumerable: false,
					writable: false
				});
				return finalized;
			} catch (_err) {
				throw new Error("Error converting schema to JSON.");
			}
		}
		function isTransforming(_schema, _ctx) {
			const ctx = _ctx ?? { seen: /* @__PURE__ */ new Set() };
			if (ctx.seen.has(_schema)) return false;
			ctx.seen.add(_schema);
			const def = _schema._zod.def;
			if (def.type === "transform") return true;
			if (def.type === "array") return isTransforming(def.element, ctx);
			if (def.type === "set") return isTransforming(def.valueType, ctx);
			if (def.type === "lazy") return isTransforming(def.getter(), ctx);
			if (def.type === "promise" || def.type === "optional" || def.type === "nonoptional" || def.type === "nullable" || def.type === "readonly" || def.type === "default" || def.type === "prefault") return isTransforming(def.innerType, ctx);
			if (def.type === "intersection") return isTransforming(def.left, ctx) || isTransforming(def.right, ctx);
			if (def.type === "record" || def.type === "map") return isTransforming(def.keyType, ctx) || isTransforming(def.valueType, ctx);
			if (def.type === "pipe") {
				if (_schema._zod.traits.has("$ZodCodec")) return true;
				return isTransforming(def.in, ctx) || isTransforming(def.out, ctx);
			}
			if (def.type === "object") {
				for (const key in def.shape) if (isTransforming(def.shape[key], ctx)) return true;
				return false;
			}
			if (def.type === "union") {
				for (const option of def.options) if (isTransforming(option, ctx)) return true;
				return false;
			}
			if (def.type === "tuple") {
				for (const item of def.items) if (isTransforming(item, ctx)) return true;
				if (def.rest && isTransforming(def.rest, ctx)) return true;
				return false;
			}
			return false;
		}
		/**
		* Creates a toJSONSchema method for a schema instance.
		* This encapsulates the logic of initializing context, processing, extracting defs, and finalizing.
		*/
		const createToJSONSchemaMethod = (schema, processors = {}) => (params) => {
			const ctx = initializeContext({
				...params,
				processors
			});
			process(schema, ctx);
			extractDefs(ctx, schema);
			return finalize(ctx, schema);
		};
		const createStandardJSONSchemaMethod = (schema, io, processors = {}) => (params) => {
			const { libraryOptions, target } = params ?? {};
			const ctx = initializeContext({
				...libraryOptions ?? {},
				target,
				io,
				processors
			});
			process(schema, ctx);
			extractDefs(ctx, schema);
			return finalize(ctx, schema);
		};
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/core/json-schema-processors.js
		const formatMap = {
			guid: "uuid",
			url: "uri",
			datetime: "date-time",
			json_string: "json-string",
			regex: ""
		};
		const stringProcessor = (schema, ctx, _json, _params) => {
			const json = _json;
			json.type = "string";
			const { minimum, maximum, format, patterns, contentEncoding } = schema._zod.bag;
			if (typeof minimum === "number") json.minLength = minimum;
			if (typeof maximum === "number") json.maxLength = maximum;
			if (format) {
				json.format = formatMap[format] ?? format;
				if (json.format === "") delete json.format;
				if (format === "time") delete json.format;
			}
			if (contentEncoding) json.contentEncoding = contentEncoding;
			if (patterns && patterns.size > 0) {
				const regexes = [...patterns];
				if (regexes.length === 1) json.pattern = regexes[0].source;
				else if (regexes.length > 1) json.allOf = [...regexes.map((regex) => ({
					...ctx.target === "draft-07" || ctx.target === "draft-04" || ctx.target === "openapi-3.0" ? { type: "string" } : {},
					pattern: regex.source
				}))];
			}
		};
		const numberProcessor = (schema, ctx, _json, _params) => {
			const json = _json;
			const { minimum, maximum, format, multipleOf, exclusiveMaximum, exclusiveMinimum } = schema._zod.bag;
			if (typeof format === "string" && format.includes("int")) json.type = "integer";
			else json.type = "number";
			const exMin = typeof exclusiveMinimum === "number" && exclusiveMinimum >= (minimum ?? Number.NEGATIVE_INFINITY);
			const exMax = typeof exclusiveMaximum === "number" && exclusiveMaximum <= (maximum ?? Number.POSITIVE_INFINITY);
			const legacy = ctx.target === "draft-04" || ctx.target === "openapi-3.0";
			if (exMin) if (legacy) {
				json.minimum = exclusiveMinimum;
				json.exclusiveMinimum = true;
			} else json.exclusiveMinimum = exclusiveMinimum;
			else if (typeof minimum === "number") json.minimum = minimum;
			if (exMax) if (legacy) {
				json.maximum = exclusiveMaximum;
				json.exclusiveMaximum = true;
			} else json.exclusiveMaximum = exclusiveMaximum;
			else if (typeof maximum === "number") json.maximum = maximum;
			if (typeof multipleOf === "number") json.multipleOf = multipleOf;
		};
		const booleanProcessor = (_schema, _ctx, json, _params) => {
			json.type = "boolean";
		};
		const nullProcessor = (_schema, ctx, json, _params) => {
			if (ctx.target === "openapi-3.0") {
				json.type = "string";
				json.nullable = true;
				json.enum = [null];
			} else json.type = "null";
		};
		const customProcessor = (_schema, ctx, _json, _params) => {
			if (ctx.unrepresentable === "throw") throw new Error("Custom types cannot be represented in JSON Schema");
		};
		const transformProcessor = (_schema, ctx, _json, _params) => {
			if (ctx.unrepresentable === "throw") throw new Error("Transforms cannot be represented in JSON Schema");
		};
		const arrayProcessor = (schema, ctx, _json, params) => {
			const json = _json;
			const def = schema._zod.def;
			const { minimum, maximum } = schema._zod.bag;
			if (typeof minimum === "number") json.minItems = minimum;
			if (typeof maximum === "number") json.maxItems = maximum;
			json.type = "array";
			json.items = process(def.element, ctx, {
				...params,
				path: [...params.path, "items"]
			});
		};
		const unionProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			const isExclusive = def.inclusive === false;
			const options = def.options.map((x, i) => process(x, ctx, {
				...params,
				path: [
					...params.path,
					isExclusive ? "oneOf" : "anyOf",
					i
				]
			}));
			if (isExclusive) json.oneOf = options;
			else json.anyOf = options;
		};
		const intersectionProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			const a = process(def.left, ctx, {
				...params,
				path: [
					...params.path,
					"allOf",
					0
				]
			});
			const b = process(def.right, ctx, {
				...params,
				path: [
					...params.path,
					"allOf",
					1
				]
			});
			const isSimpleIntersection = (val) => "allOf" in val && Object.keys(val).length === 1;
			json.allOf = [...isSimpleIntersection(a) ? a.allOf : [a], ...isSimpleIntersection(b) ? b.allOf : [b]];
		};
		const recordProcessor = (schema, ctx, _json, params) => {
			const json = _json;
			const def = schema._zod.def;
			json.type = "object";
			const keyType = def.keyType;
			const patterns = keyType._zod.bag?.patterns;
			if (def.mode === "loose" && patterns && patterns.size > 0) {
				const valueSchema = process(def.valueType, ctx, {
					...params,
					path: [
						...params.path,
						"patternProperties",
						"*"
					]
				});
				json.patternProperties = {};
				for (const pattern of patterns) json.patternProperties[pattern.source] = valueSchema;
			} else {
				if (ctx.target === "draft-07" || ctx.target === "draft-2020-12") json.propertyNames = process(def.keyType, ctx, {
					...params,
					path: [...params.path, "propertyNames"]
				});
				json.additionalProperties = process(def.valueType, ctx, {
					...params,
					path: [...params.path, "additionalProperties"]
				});
			}
			const keyValues = keyType._zod.values;
			if (keyValues) {
				const validKeyValues = [...keyValues].filter((v) => typeof v === "string" || typeof v === "number");
				if (validKeyValues.length > 0) json.required = validKeyValues;
			}
		};
		const nullableProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			const inner = process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			if (ctx.target === "openapi-3.0") {
				seen.ref = def.innerType;
				json.nullable = true;
			} else json.anyOf = [inner, { type: "null" }];
		};
		const nonoptionalProcessor = (schema, ctx, _json, params) => {
			const def = schema._zod.def;
			process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = def.innerType;
		};
		const defaultProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = def.innerType;
			json.default = JSON.parse(JSON.stringify(def.defaultValue));
		};
		const prefaultProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = def.innerType;
			if (ctx.io === "input") json._prefault = JSON.parse(JSON.stringify(def.defaultValue));
		};
		const catchProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = def.innerType;
			let catchValue;
			try {
				catchValue = def.catchValue(void 0);
			} catch {
				throw new Error("Dynamic catch values are not supported in JSON Schema");
			}
			json.default = catchValue;
		};
		const pipeProcessor = (schema, ctx, _json, params) => {
			const def = schema._zod.def;
			const inIsTransform = def.in._zod.traits.has("$ZodTransform");
			const innerType = ctx.io === "input" ? inIsTransform ? def.out : def.in : def.out;
			process(innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = innerType;
		};
		const readonlyProcessor = (schema, ctx, json, params) => {
			const def = schema._zod.def;
			process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = def.innerType;
			json.readOnly = true;
		};
		const optionalProcessor = (schema, ctx, _json, params) => {
			const def = schema._zod.def;
			process(def.innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = def.innerType;
		};
		const lazyProcessor = (schema, ctx, _json, params) => {
			const innerType = schema._zod.innerType;
			process(innerType, ctx, params);
			const seen = ctx.seen.get(schema);
			seen.ref = innerType;
		};
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/classic/iso.js
		const ZodISODateTime = /*@__PURE__*/ $constructor("ZodISODateTime", (inst, def) => {
			$ZodISODateTime.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		function datetime(params) {
			return /* @__PURE__ */ _isoDateTime(ZodISODateTime, params);
		}
		const ZodISODate = /*@__PURE__*/ $constructor("ZodISODate", (inst, def) => {
			$ZodISODate.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		function date(params) {
			return /* @__PURE__ */ _isoDate(ZodISODate, params);
		}
		const ZodISOTime = /*@__PURE__*/ $constructor("ZodISOTime", (inst, def) => {
			$ZodISOTime.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		function time(params) {
			return /* @__PURE__ */ _isoTime(ZodISOTime, params);
		}
		const ZodISODuration = /*@__PURE__*/ $constructor("ZodISODuration", (inst, def) => {
			$ZodISODuration.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		function duration(params) {
			return /* @__PURE__ */ _isoDuration(ZodISODuration, params);
		}
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/classic/errors.js
		const initializer = (inst, issues) => {
			$ZodError.init(inst, issues);
			inst.name = "ZodError";
			Object.defineProperties(inst, {
				format: { value: (mapper) => formatError(inst, mapper) },
				flatten: { value: (mapper) => flattenError(inst, mapper) },
				addIssue: { value: (issue) => {
					inst.issues.push(issue);
					inst.message = JSON.stringify(inst.issues, jsonStringifyReplacer, 2);
				} },
				addIssues: { value: (issues) => {
					inst.issues.push(...issues);
					inst.message = JSON.stringify(inst.issues, jsonStringifyReplacer, 2);
				} },
				isEmpty: { get() {
					return inst.issues.length === 0;
				} }
			});
		};
		const ZodRealError = /*@__PURE__*/ $constructor("ZodError", initializer, { Parent: Error });
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/classic/parse.js
		const parse = /* @__PURE__ */ _parse(ZodRealError);
		const parseAsync = /* @__PURE__ */ _parseAsync(ZodRealError);
		const safeParse = /* @__PURE__ */ _safeParse(ZodRealError);
		const safeParseAsync = /* @__PURE__ */ _safeParseAsync(ZodRealError);
		const encode = /* @__PURE__ */ _encode(ZodRealError);
		const decode = /* @__PURE__ */ _decode(ZodRealError);
		const encodeAsync = /* @__PURE__ */ _encodeAsync(ZodRealError);
		const decodeAsync = /* @__PURE__ */ _decodeAsync(ZodRealError);
		const safeEncode = /* @__PURE__ */ _safeEncode(ZodRealError);
		const safeDecode = /* @__PURE__ */ _safeDecode(ZodRealError);
		const safeEncodeAsync = /* @__PURE__ */ _safeEncodeAsync(ZodRealError);
		const safeDecodeAsync = /* @__PURE__ */ _safeDecodeAsync(ZodRealError);
		//#endregion
		//#region ../../../node_modules/.pnpm/zod@4.4.3/node_modules/zod/v4/classic/schemas.js
		const _installedGroups = /* @__PURE__ */ new WeakMap();
		function _installLazyMethods(inst, group, methods) {
			const proto = Object.getPrototypeOf(inst);
			let installed = _installedGroups.get(proto);
			if (!installed) {
				installed = /* @__PURE__ */ new Set();
				_installedGroups.set(proto, installed);
			}
			if (installed.has(group)) return;
			installed.add(group);
			for (const key in methods) {
				const fn = methods[key];
				Object.defineProperty(proto, key, {
					configurable: true,
					enumerable: false,
					get() {
						const bound = fn.bind(this);
						Object.defineProperty(this, key, {
							configurable: true,
							writable: true,
							enumerable: true,
							value: bound
						});
						return bound;
					},
					set(v) {
						Object.defineProperty(this, key, {
							configurable: true,
							writable: true,
							enumerable: true,
							value: v
						});
					}
				});
			}
		}
		const ZodType = /*@__PURE__*/ $constructor("ZodType", (inst, def) => {
			$ZodType.init(inst, def);
			Object.assign(inst["~standard"], { jsonSchema: {
				input: createStandardJSONSchemaMethod(inst, "input"),
				output: createStandardJSONSchemaMethod(inst, "output")
			} });
			inst.toJSONSchema = createToJSONSchemaMethod(inst, {});
			inst.def = def;
			inst.type = def.type;
			Object.defineProperty(inst, "_def", { value: def });
			inst.parse = (data, params) => parse(inst, data, params, { callee: inst.parse });
			inst.safeParse = (data, params) => safeParse(inst, data, params);
			inst.parseAsync = async (data, params) => parseAsync(inst, data, params, { callee: inst.parseAsync });
			inst.safeParseAsync = async (data, params) => safeParseAsync(inst, data, params);
			inst.spa = inst.safeParseAsync;
			inst.encode = (data, params) => encode(inst, data, params);
			inst.decode = (data, params) => decode(inst, data, params);
			inst.encodeAsync = async (data, params) => encodeAsync(inst, data, params);
			inst.decodeAsync = async (data, params) => decodeAsync(inst, data, params);
			inst.safeEncode = (data, params) => safeEncode(inst, data, params);
			inst.safeDecode = (data, params) => safeDecode(inst, data, params);
			inst.safeEncodeAsync = async (data, params) => safeEncodeAsync(inst, data, params);
			inst.safeDecodeAsync = async (data, params) => safeDecodeAsync(inst, data, params);
			_installLazyMethods(inst, "ZodType", {
				check(...chks) {
					const def = this.def;
					return this.clone(mergeDefs(def, { checks: [...def.checks ?? [], ...chks.map((ch) => typeof ch === "function" ? { _zod: {
						check: ch,
						def: { check: "custom" },
						onattach: []
					} } : ch)] }), { parent: true });
				},
				with(...chks) {
					return this.check(...chks);
				},
				clone(def, params) {
					return clone(this, def, params);
				},
				brand() {
					return this;
				},
				register(reg, meta) {
					reg.add(this, meta);
					return this;
				},
				refine(check, params) {
					return this.check(refine(check, params));
				},
				superRefine(refinement, params) {
					return this.check(superRefine(refinement, params));
				},
				overwrite(fn) {
					return this.check(/* @__PURE__ */ _overwrite(fn));
				},
				optional() {
					return optional(this);
				},
				exactOptional() {
					return exactOptional(this);
				},
				nullable() {
					return nullable(this);
				},
				nullish() {
					return optional(nullable(this));
				},
				nonoptional(params) {
					return nonoptional(this, params);
				},
				array() {
					return array(this);
				},
				or(arg) {
					return union([this, arg]);
				},
				and(arg) {
					return intersection(this, arg);
				},
				transform(tx) {
					return pipe(this, transform(tx));
				},
				default(d) {
					return _default(this, d);
				},
				prefault(d) {
					return prefault(this, d);
				},
				catch(params) {
					return _catch(this, params);
				},
				pipe(target) {
					return pipe(this, target);
				},
				readonly() {
					return readonly(this);
				},
				describe(description) {
					const cl = this.clone();
					globalRegistry.add(cl, { description });
					return cl;
				},
				meta(...args) {
					if (args.length === 0) return globalRegistry.get(this);
					const cl = this.clone();
					globalRegistry.add(cl, args[0]);
					return cl;
				},
				isOptional() {
					return this.safeParse(void 0).success;
				},
				isNullable() {
					return this.safeParse(null).success;
				},
				apply(fn) {
					return fn(this);
				}
			});
			Object.defineProperty(inst, "description", {
				get() {
					return globalRegistry.get(inst)?.description;
				},
				configurable: true
			});
			return inst;
		});
		/** @internal */
		const _ZodString = /*@__PURE__*/ $constructor("_ZodString", (inst, def) => {
			$ZodString.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => stringProcessor(inst, ctx, json, params);
			const bag = inst._zod.bag;
			inst.format = bag.format ?? null;
			inst.minLength = bag.minimum ?? null;
			inst.maxLength = bag.maximum ?? null;
			_installLazyMethods(inst, "_ZodString", {
				regex(...args) {
					return this.check(/* @__PURE__ */ _regex(...args));
				},
				includes(...args) {
					return this.check(/* @__PURE__ */ _includes(...args));
				},
				startsWith(...args) {
					return this.check(/* @__PURE__ */ _startsWith(...args));
				},
				endsWith(...args) {
					return this.check(/* @__PURE__ */ _endsWith(...args));
				},
				min(...args) {
					return this.check(/* @__PURE__ */ _minLength(...args));
				},
				max(...args) {
					return this.check(/* @__PURE__ */ _maxLength(...args));
				},
				length(...args) {
					return this.check(/* @__PURE__ */ _length(...args));
				},
				nonempty(...args) {
					return this.check(/* @__PURE__ */ _minLength(1, ...args));
				},
				lowercase(params) {
					return this.check(/* @__PURE__ */ _lowercase(params));
				},
				uppercase(params) {
					return this.check(/* @__PURE__ */ _uppercase(params));
				},
				trim() {
					return this.check(/* @__PURE__ */ _trim());
				},
				normalize(...args) {
					return this.check(/* @__PURE__ */ _normalize(...args));
				},
				toLowerCase() {
					return this.check(/* @__PURE__ */ _toLowerCase());
				},
				toUpperCase() {
					return this.check(/* @__PURE__ */ _toUpperCase());
				},
				slugify() {
					return this.check(/* @__PURE__ */ _slugify());
				}
			});
		});
		const ZodString = /*@__PURE__*/ $constructor("ZodString", (inst, def) => {
			$ZodString.init(inst, def);
			_ZodString.init(inst, def);
			inst.email = (params) => inst.check(/* @__PURE__ */ _email(ZodEmail, params));
			inst.url = (params) => inst.check(/* @__PURE__ */ _url(ZodURL, params));
			inst.jwt = (params) => inst.check(/* @__PURE__ */ _jwt(ZodJWT, params));
			inst.emoji = (params) => inst.check(/* @__PURE__ */ _emoji(ZodEmoji, params));
			inst.guid = (params) => inst.check(/* @__PURE__ */ _guid(ZodGUID, params));
			inst.uuid = (params) => inst.check(/* @__PURE__ */ _uuid(ZodUUID, params));
			inst.uuidv4 = (params) => inst.check(/* @__PURE__ */ _uuidv4(ZodUUID, params));
			inst.uuidv6 = (params) => inst.check(/* @__PURE__ */ _uuidv6(ZodUUID, params));
			inst.uuidv7 = (params) => inst.check(/* @__PURE__ */ _uuidv7(ZodUUID, params));
			inst.nanoid = (params) => inst.check(/* @__PURE__ */ _nanoid(ZodNanoID, params));
			inst.guid = (params) => inst.check(/* @__PURE__ */ _guid(ZodGUID, params));
			inst.cuid = (params) => inst.check(/* @__PURE__ */ _cuid(ZodCUID, params));
			inst.cuid2 = (params) => inst.check(/* @__PURE__ */ _cuid2(ZodCUID2, params));
			inst.ulid = (params) => inst.check(/* @__PURE__ */ _ulid(ZodULID, params));
			inst.base64 = (params) => inst.check(/* @__PURE__ */ _base64(ZodBase64, params));
			inst.base64url = (params) => inst.check(/* @__PURE__ */ _base64url(ZodBase64URL, params));
			inst.xid = (params) => inst.check(/* @__PURE__ */ _xid(ZodXID, params));
			inst.ksuid = (params) => inst.check(/* @__PURE__ */ _ksuid(ZodKSUID, params));
			inst.ipv4 = (params) => inst.check(/* @__PURE__ */ _ipv4(ZodIPv4, params));
			inst.ipv6 = (params) => inst.check(/* @__PURE__ */ _ipv6(ZodIPv6, params));
			inst.cidrv4 = (params) => inst.check(/* @__PURE__ */ _cidrv4(ZodCIDRv4, params));
			inst.cidrv6 = (params) => inst.check(/* @__PURE__ */ _cidrv6(ZodCIDRv6, params));
			inst.e164 = (params) => inst.check(/* @__PURE__ */ _e164(ZodE164, params));
			inst.datetime = (params) => inst.check(datetime(params));
			inst.date = (params) => inst.check(date(params));
			inst.time = (params) => inst.check(time(params));
			inst.duration = (params) => inst.check(duration(params));
		});
		function string(params) {
			return /* @__PURE__ */ _string(ZodString, params);
		}
		const ZodStringFormat = /*@__PURE__*/ $constructor("ZodStringFormat", (inst, def) => {
			$ZodStringFormat.init(inst, def);
			_ZodString.init(inst, def);
		});
		const ZodEmail = /*@__PURE__*/ $constructor("ZodEmail", (inst, def) => {
			$ZodEmail.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodGUID = /*@__PURE__*/ $constructor("ZodGUID", (inst, def) => {
			$ZodGUID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodUUID = /*@__PURE__*/ $constructor("ZodUUID", (inst, def) => {
			$ZodUUID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodURL = /*@__PURE__*/ $constructor("ZodURL", (inst, def) => {
			$ZodURL.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodEmoji = /*@__PURE__*/ $constructor("ZodEmoji", (inst, def) => {
			$ZodEmoji.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodNanoID = /*@__PURE__*/ $constructor("ZodNanoID", (inst, def) => {
			$ZodNanoID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		/**
		* @deprecated CUID v1 is deprecated by its authors due to information leakage
		* (timestamps embedded in the id). Use {@link ZodCUID2} instead.
		* See https://github.com/paralleldrive/cuid.
		*/
		const ZodCUID = /*@__PURE__*/ $constructor("ZodCUID", (inst, def) => {
			$ZodCUID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodCUID2 = /*@__PURE__*/ $constructor("ZodCUID2", (inst, def) => {
			$ZodCUID2.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodULID = /*@__PURE__*/ $constructor("ZodULID", (inst, def) => {
			$ZodULID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodXID = /*@__PURE__*/ $constructor("ZodXID", (inst, def) => {
			$ZodXID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodKSUID = /*@__PURE__*/ $constructor("ZodKSUID", (inst, def) => {
			$ZodKSUID.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodIPv4 = /*@__PURE__*/ $constructor("ZodIPv4", (inst, def) => {
			$ZodIPv4.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodIPv6 = /*@__PURE__*/ $constructor("ZodIPv6", (inst, def) => {
			$ZodIPv6.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodCIDRv4 = /*@__PURE__*/ $constructor("ZodCIDRv4", (inst, def) => {
			$ZodCIDRv4.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodCIDRv6 = /*@__PURE__*/ $constructor("ZodCIDRv6", (inst, def) => {
			$ZodCIDRv6.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodBase64 = /*@__PURE__*/ $constructor("ZodBase64", (inst, def) => {
			$ZodBase64.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodBase64URL = /*@__PURE__*/ $constructor("ZodBase64URL", (inst, def) => {
			$ZodBase64URL.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodE164 = /*@__PURE__*/ $constructor("ZodE164", (inst, def) => {
			$ZodE164.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodJWT = /*@__PURE__*/ $constructor("ZodJWT", (inst, def) => {
			$ZodJWT.init(inst, def);
			ZodStringFormat.init(inst, def);
		});
		const ZodNumber = /*@__PURE__*/ $constructor("ZodNumber", (inst, def) => {
			$ZodNumber.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => numberProcessor(inst, ctx, json, params);
			_installLazyMethods(inst, "ZodNumber", {
				gt(value, params) {
					return this.check(/* @__PURE__ */ _gt(value, params));
				},
				gte(value, params) {
					return this.check(/* @__PURE__ */ _gte(value, params));
				},
				min(value, params) {
					return this.check(/* @__PURE__ */ _gte(value, params));
				},
				lt(value, params) {
					return this.check(/* @__PURE__ */ _lt(value, params));
				},
				lte(value, params) {
					return this.check(/* @__PURE__ */ _lte(value, params));
				},
				max(value, params) {
					return this.check(/* @__PURE__ */ _lte(value, params));
				},
				int(params) {
					return this.check(int(params));
				},
				safe(params) {
					return this.check(int(params));
				},
				positive(params) {
					return this.check(/* @__PURE__ */ _gt(0, params));
				},
				nonnegative(params) {
					return this.check(/* @__PURE__ */ _gte(0, params));
				},
				negative(params) {
					return this.check(/* @__PURE__ */ _lt(0, params));
				},
				nonpositive(params) {
					return this.check(/* @__PURE__ */ _lte(0, params));
				},
				multipleOf(value, params) {
					return this.check(/* @__PURE__ */ _multipleOf(value, params));
				},
				step(value, params) {
					return this.check(/* @__PURE__ */ _multipleOf(value, params));
				},
				finite() {
					return this;
				}
			});
			const bag = inst._zod.bag;
			inst.minValue = Math.max(bag.minimum ?? Number.NEGATIVE_INFINITY, bag.exclusiveMinimum ?? Number.NEGATIVE_INFINITY) ?? null;
			inst.maxValue = Math.min(bag.maximum ?? Number.POSITIVE_INFINITY, bag.exclusiveMaximum ?? Number.POSITIVE_INFINITY) ?? null;
			inst.isInt = (bag.format ?? "").includes("int") || Number.isSafeInteger(bag.multipleOf ?? .5);
			inst.isFinite = true;
			inst.format = bag.format ?? null;
		});
		function number(params) {
			return /* @__PURE__ */ _number(ZodNumber, params);
		}
		const ZodNumberFormat = /*@__PURE__*/ $constructor("ZodNumberFormat", (inst, def) => {
			$ZodNumberFormat.init(inst, def);
			ZodNumber.init(inst, def);
		});
		function int(params) {
			return /* @__PURE__ */ _int(ZodNumberFormat, params);
		}
		const ZodBoolean = /*@__PURE__*/ $constructor("ZodBoolean", (inst, def) => {
			$ZodBoolean.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => booleanProcessor(inst, ctx, json, params);
		});
		function boolean(params) {
			return /* @__PURE__ */ _boolean(ZodBoolean, params);
		}
		const ZodNull = /*@__PURE__*/ $constructor("ZodNull", (inst, def) => {
			$ZodNull.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => nullProcessor(inst, ctx, json, params);
		});
		function _null(params) {
			return /* @__PURE__ */ _null$1(ZodNull, params);
		}
		const ZodArray = /*@__PURE__*/ $constructor("ZodArray", (inst, def) => {
			$ZodArray.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => arrayProcessor(inst, ctx, json, params);
			inst.element = def.element;
			_installLazyMethods(inst, "ZodArray", {
				min(n, params) {
					return this.check(/* @__PURE__ */ _minLength(n, params));
				},
				nonempty(params) {
					return this.check(/* @__PURE__ */ _minLength(1, params));
				},
				max(n, params) {
					return this.check(/* @__PURE__ */ _maxLength(n, params));
				},
				length(n, params) {
					return this.check(/* @__PURE__ */ _length(n, params));
				},
				unwrap() {
					return this.element;
				}
			});
		});
		function array(element, params) {
			return /* @__PURE__ */ _array(ZodArray, element, params);
		}
		const ZodUnion = /*@__PURE__*/ $constructor("ZodUnion", (inst, def) => {
			$ZodUnion.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => unionProcessor(inst, ctx, json, params);
			inst.options = def.options;
		});
		function union(options, params) {
			return new ZodUnion({
				type: "union",
				options,
				...normalizeParams(params)
			});
		}
		const ZodIntersection = /*@__PURE__*/ $constructor("ZodIntersection", (inst, def) => {
			$ZodIntersection.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => intersectionProcessor(inst, ctx, json, params);
		});
		function intersection(left, right) {
			return new ZodIntersection({
				type: "intersection",
				left,
				right
			});
		}
		const ZodRecord = /*@__PURE__*/ $constructor("ZodRecord", (inst, def) => {
			$ZodRecord.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => recordProcessor(inst, ctx, json, params);
			inst.keyType = def.keyType;
			inst.valueType = def.valueType;
		});
		function record$1(keyType, valueType, params) {
			if (!valueType || !valueType._zod) return new ZodRecord({
				type: "record",
				keyType: string(),
				valueType: keyType,
				...normalizeParams(valueType)
			});
			return new ZodRecord({
				type: "record",
				keyType,
				valueType,
				...normalizeParams(params)
			});
		}
		const ZodTransform = /*@__PURE__*/ $constructor("ZodTransform", (inst, def) => {
			$ZodTransform.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => transformProcessor(inst, ctx, json, params);
			inst._zod.parse = (payload, _ctx) => {
				if (_ctx.direction === "backward") throw new $ZodEncodeError(inst.constructor.name);
				payload.addIssue = (issue$1) => {
					if (typeof issue$1 === "string") payload.issues.push(issue(issue$1, payload.value, def));
					else {
						const _issue = issue$1;
						if (_issue.fatal) _issue.continue = false;
						_issue.code ?? (_issue.code = "custom");
						_issue.input ?? (_issue.input = payload.value);
						_issue.inst ?? (_issue.inst = inst);
						payload.issues.push(issue(_issue));
					}
				};
				const output = def.transform(payload.value, payload);
				if (output instanceof Promise) return output.then((output) => {
					payload.value = output;
					payload.fallback = true;
					return payload;
				});
				payload.value = output;
				payload.fallback = true;
				return payload;
			};
		});
		function transform(fn) {
			return new ZodTransform({
				type: "transform",
				transform: fn
			});
		}
		const ZodOptional = /*@__PURE__*/ $constructor("ZodOptional", (inst, def) => {
			$ZodOptional.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => optionalProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
		});
		function optional(innerType) {
			return new ZodOptional({
				type: "optional",
				innerType
			});
		}
		const ZodExactOptional = /*@__PURE__*/ $constructor("ZodExactOptional", (inst, def) => {
			$ZodExactOptional.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => optionalProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
		});
		function exactOptional(innerType) {
			return new ZodExactOptional({
				type: "optional",
				innerType
			});
		}
		const ZodNullable = /*@__PURE__*/ $constructor("ZodNullable", (inst, def) => {
			$ZodNullable.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => nullableProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
		});
		function nullable(innerType) {
			return new ZodNullable({
				type: "nullable",
				innerType
			});
		}
		const ZodDefault = /*@__PURE__*/ $constructor("ZodDefault", (inst, def) => {
			$ZodDefault.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => defaultProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
			inst.removeDefault = inst.unwrap;
		});
		function _default(innerType, defaultValue) {
			return new ZodDefault({
				type: "default",
				innerType,
				get defaultValue() {
					return typeof defaultValue === "function" ? defaultValue() : shallowClone(defaultValue);
				}
			});
		}
		const ZodPrefault = /*@__PURE__*/ $constructor("ZodPrefault", (inst, def) => {
			$ZodPrefault.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => prefaultProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
		});
		function prefault(innerType, defaultValue) {
			return new ZodPrefault({
				type: "prefault",
				innerType,
				get defaultValue() {
					return typeof defaultValue === "function" ? defaultValue() : shallowClone(defaultValue);
				}
			});
		}
		const ZodNonOptional = /*@__PURE__*/ $constructor("ZodNonOptional", (inst, def) => {
			$ZodNonOptional.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => nonoptionalProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
		});
		function nonoptional(innerType, params) {
			return new ZodNonOptional({
				type: "nonoptional",
				innerType,
				...normalizeParams(params)
			});
		}
		const ZodCatch = /*@__PURE__*/ $constructor("ZodCatch", (inst, def) => {
			$ZodCatch.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => catchProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
			inst.removeCatch = inst.unwrap;
		});
		function _catch(innerType, catchValue) {
			return new ZodCatch({
				type: "catch",
				innerType,
				catchValue: typeof catchValue === "function" ? catchValue : () => catchValue
			});
		}
		const ZodPipe = /*@__PURE__*/ $constructor("ZodPipe", (inst, def) => {
			$ZodPipe.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => pipeProcessor(inst, ctx, json, params);
			inst.in = def.in;
			inst.out = def.out;
		});
		function pipe(in_, out) {
			return new ZodPipe({
				type: "pipe",
				in: in_,
				out
			});
		}
		const ZodReadonly = /*@__PURE__*/ $constructor("ZodReadonly", (inst, def) => {
			$ZodReadonly.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => readonlyProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.innerType;
		});
		function readonly(innerType) {
			return new ZodReadonly({
				type: "readonly",
				innerType
			});
		}
		const ZodLazy = /*@__PURE__*/ $constructor("ZodLazy", (inst, def) => {
			$ZodLazy.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => lazyProcessor(inst, ctx, json, params);
			inst.unwrap = () => inst._zod.def.getter();
		});
		function lazy(getter) {
			return new ZodLazy({
				type: "lazy",
				getter
			});
		}
		const ZodCustom = /*@__PURE__*/ $constructor("ZodCustom", (inst, def) => {
			$ZodCustom.init(inst, def);
			ZodType.init(inst, def);
			inst._zod.processJSONSchema = (ctx, json, params) => customProcessor(inst, ctx, json, params);
		});
		function refine(fn, _params = {}) {
			return /* @__PURE__ */ _refine(ZodCustom, fn, _params);
		}
		function superRefine(fn, params) {
			return /* @__PURE__ */ _superRefine(fn, params);
		}
		function json$1(params) {
			const jsonSchema = lazy(() => {
				return union([
					string(params),
					number(),
					boolean(),
					_null(),
					array(jsonSchema),
					record$1(string(), jsonSchema)
				]);
			});
			return jsonSchema;
		}
		//#endregion
		//#region src/remote.mjs
		const method = (name, parameters, cancellable = false) => ({
			id: `@thaliris/dsh-plugin#thaliris/${name}`,
			service: "thalirisController",
			namespace: "thaliris",
			method: name,
			invocation: { kind: "direct" },
			parameters: parameters.map((name) => ({
				name,
				wire: name,
				source: "json",
				codec: {
					mode: "strict",
					typeSymbol: "@thaliris/dsh-plugin#NativeIdentity",
					create: () => string().trim().min(1).max(128)
				}
			})),
			...cancellable ? { cancellation: { parameter: "signal" } } : {},
			result: {
				mode: "strict",
				typeSymbol: "@thaliris/dsh-plugin#JsonValue",
				create: () => json$1(),
				decode: (value) => json$1().parse(value)
			}
		});
		const remoteContribution = {
			package: "@thaliris/dsh-plugin",
			descriptors: [
				method("templates", []),
				method("providers", []),
				method("toolCatalog", []),
				method("diagnostics", ["sessionId"], true),
				method("approveMemory", ["sessionId", "proposalId"], true)
			]
		};
		//#endregion
		//#region src/client/policy-controller.ts
		/** Revision-fenced drafts over the native Thaliris ConfigForm. */
		function copyRole(value) {
			return {
				id: value.id ?? "",
				name: value.name ?? "",
				description: value.description ?? "",
				prompt: value.prompt ?? "",
				enabled: value.enabled ?? true,
				tools: [...value.tools ?? []],
				modelPolicy: {
					mode: value.modelPolicy?.mode ?? "inherit",
					routes: structuredClone(value.modelPolicy?.routes ?? [])
				},
				memory: {
					read: [...value.memory?.read ?? []],
					write: [...value.memory?.write ?? []]
				},
				context: {
					handoff: value.context?.handoff ?? true,
					memory: value.context?.memory ?? false
				}
			};
		}
		/** Fill schema-resolved defaults while keeping the native form authoritative. */
		function copyPolicy(value) {
			if (value === void 0) return void 0;
			return {
				controllerPrompt: value.controllerPrompt ?? "",
				workspaces: structuredClone(value.workspaces ?? []),
				roles: (value.roles ?? []).map((role) => copyRole(role)),
				memory: {
					mode: value.memory?.mode ?? "disabled",
					autoAuthorized: value.memory?.autoAuthorized ?? false,
					providers: [...value.memory?.providers ?? []],
					controllerRead: [...value.memory?.controllerRead ?? []],
					controllerWrite: [...value.memory?.controllerWrite ?? []]
				}
			};
		}
		function validationError(policy) {
			if (policy === void 0) return void 0;
			const ids = policy.roles.map((role) => role.id.trim());
			if (ids.some((id) => id.length === 0)) return "Role IDs cannot be empty.";
			if (new Set(ids).size !== ids.length) return "Each role needs a unique ID.";
			if (policy.roles.some((role) => role.modelPolicy.mode === "fixed" && role.modelPolicy.routes.length !== 1)) return "A fixed model policy needs exactly one allowed route.";
		}
		/** Owns only transient drafts; every accepted value and write remains in native Settings. */
		var PolicyEditorController = class {
			form;
			store;
			dirtyFields = /* @__PURE__ */ new Set();
			draft;
			expectedRevision;
			saving = false;
			conflict = false;
			error;
			native;
			unsubscribe;
			constructor(form) {
				this.form = form;
				this.native = form.getSnapshot();
				this.draft = copyPolicy(this.native.value?.policy);
				this.store = (0, _deepseek_ai_dsh_client_store.createSnapshotStore)(this.project());
				this.unsubscribe = form.subscribe(() => this.onNativeChange());
			}
			getSnapshot = () => this.store.getSnapshot();
			subscribe = (listener) => this.store.subscribe(listener);
			edit(field, value) {
				if (!this.canEdit()) return;
				if (this.expectedRevision === void 0) this.expectedRevision = this.native.revision;
				const draft = copyPolicy(this.draft);
				if (draft === void 0) return;
				draft[field] = structuredClone(value);
				this.draft = draft;
				this.dirtyFields.add(field);
				this.error = void 0;
				this.conflict = this.native.revision !== this.expectedRevision;
				this.publish();
			}
			async save() {
				const current = this.project();
				if (!current.dirty || !current.writable || current.conflict || current.validationError || this.saving || this.expectedRevision === void 0 || this.draft === void 0) return false;
				const revision = this.expectedRevision;
				const operations = [...this.dirtyFields].map((field) => ({
					op: "set",
					path: ["policy", field],
					value: json$1().parse(this.draft[field])
				}));
				this.saving = true;
				this.error = void 0;
				this.publish();
				try {
					if (!await this.form.mutate(operations, revision)) {
						this.conflict = true;
						this.error = "The native Settings revision changed. Reload its latest values before editing again.";
						return false;
					}
					this.dirtyFields.clear();
					this.expectedRevision = void 0;
					this.conflict = false;
					this.draft = copyPolicy(this.form.getSnapshot().value?.policy);
					return true;
				} catch (error) {
					this.error = error instanceof Error ? error.message : String(error);
					return false;
				} finally {
					this.saving = false;
					this.native = this.form.getSnapshot();
					this.publish();
				}
			}
			/** Drop this page's drafts and re-read the latest native snapshot. */
			discard() {
				this.native = this.form.getSnapshot();
				this.draft = copyPolicy(this.native.value?.policy);
				this.expectedRevision = void 0;
				this.dirtyFields.clear();
				this.saving = false;
				this.conflict = false;
				this.error = void 0;
				this.publish();
			}
			async dispose() {
				this.unsubscribe();
			}
			canEdit() {
				return this.native.status === "ready" && this.native.writable && this.native.mode === "host" && !this.saving && !this.conflict && this.draft !== void 0 && this.native.revision !== void 0;
			}
			onNativeChange() {
				this.native = this.form.getSnapshot();
				if (this.saving) {
					this.publish();
					return;
				}
				if (this.dirtyFields.size === 0) this.draft = copyPolicy(this.native.value?.policy);
				else if (this.native.revision !== this.expectedRevision) this.conflict = true;
				this.publish();
			}
			project() {
				const writable = this.native.status === "ready" && this.native.writable && this.native.mode === "host";
				const dirtyFields = [...this.dirtyFields];
				return {
					native: this.native,
					draft: this.draft,
					dirtyFields,
					saving: this.saving,
					conflict: this.conflict,
					error: this.error,
					validationError: validationError(this.draft),
					dirty: dirtyFields.length > 0,
					writable,
					available: this.native.status === "ready" && this.draft !== void 0
				};
			}
			publish() {
				this.store.set(this.project());
			}
		};
		//#endregion
		//#region src/client/native-controller.ts
		/** Native DSH projections and the optional Thaliris Gateway contribution. */
		function describeError(value) {
			if (typeof value === "string") return value;
			if (typeof value === "object" && value !== null) {
				const record = value;
				const detail = [record.code, record.message].filter((part) => typeof part === "string").join(": ");
				if (detail) return detail;
			}
			return value instanceof Error ? value.message : String(value);
		}
		function remoteError(response) {
			return describeError(response.error);
		}
		/** Browser-side cache of Host projections; it stores no policy or task state. */
		var NativeProjectionController = class {
			ctx;
			store;
			stops;
			constructor(ctx) {
				this.ctx = ctx;
				const sessions = ctx.sessions;
				const workspaces = ctx.workspaces;
				this.store = (0, _deepseek_ai_dsh_client_store.createSnapshotStore)({
					modelCatalog: void 0,
					modelStatus: "idle",
					providers: [],
					providerStatus: "idle",
					tools: [],
					toolStatus: "idle",
					templates: [],
					templateStatus: "idle",
					sessions: sessions.list.getSnapshot(),
					workspaces: workspaces.list.getSnapshot(),
					diagnosticSessionId: void 0,
					diagnostics: void 0,
					diagnosticStatus: "idle",
					diagnosticError: void 0,
					approvalStatus: "idle",
					approvalReceipt: void 0,
					approvalError: void 0
				});
				const refreshModels = () => {
					this.loadModels();
				};
				const refreshAll = () => {
					this.refresh();
				};
				this.stops = [
					sessions.list.subscribe(() => {
						this.store.update((state) => {
							state.sessions = sessions.list.getSnapshot();
						});
					}),
					workspaces.list.subscribe(() => {
						this.store.update((state) => {
							state.workspaces = workspaces.list.getSnapshot();
						});
					}),
					ctx.remote.$on("llm/adapters-updated", refreshModels),
					ctx.remote.$on("settings/document-updated", refreshModels),
					ctx.on("connection/reset", refreshAll)
				];
			}
			getSnapshot = () => this.store.getSnapshot();
			subscribe = (listener) => this.store.subscribe(listener);
			async refresh() {
				await Promise.all([
					this.loadModels(),
					this.loadProviders(),
					this.loadTools(),
					this.loadTemplates()
				]);
			}
			async loadModels() {
				this.store.update((state) => {
					state.modelStatus = "loading";
				});
				try {
					const catalog = await this.ctx.remote.session.modelCatalog();
					this.store.update((state) => {
						state.modelCatalog = catalog;
						state.modelStatus = "ready";
					});
				} catch {
					this.store.update((state) => {
						state.modelStatus = "error";
					});
				}
			}
			async loadProviders() {
				this.store.update((state) => {
					state.providerStatus = "loading";
				});
				try {
					const response = await this.ctx.remote.thaliris.providers();
					if (!response.ok) throw new Error(remoteError(response));
					this.store.update((state) => {
						state.providers = response.value;
						state.providerStatus = "ready";
					});
				} catch {
					this.store.update((state) => {
						state.providerStatus = "error";
					});
				}
			}
			async loadTools() {
				this.store.update((state) => {
					state.toolStatus = "loading";
				});
				try {
					const response = await this.ctx.remote.thaliris.toolCatalog();
					if (!response.ok) throw new Error(remoteError(response));
					this.store.update((state) => {
						state.tools = response.value;
						state.toolStatus = "ready";
					});
				} catch {
					this.store.update((state) => {
						state.toolStatus = "error";
					});
				}
			}
			async loadTemplates() {
				this.store.update((state) => {
					state.templateStatus = "loading";
				});
				try {
					const response = await this.ctx.remote.thaliris.templates();
					if (!response.ok) throw new Error(remoteError(response));
					this.store.update((state) => {
						state.templates = response.value;
						state.templateStatus = "ready";
					});
				} catch {
					this.store.update((state) => {
						state.templateStatus = "error";
					});
				}
			}
			async loadDiagnostics(sessionId) {
				this.store.update((state) => {
					state.diagnosticSessionId = sessionId;
					state.diagnosticStatus = "loading";
					state.diagnosticError = void 0;
					state.diagnostics = void 0;
				});
				try {
					const response = await this.ctx.sessions.using(sessionId, { source: "gateway" }, async () => {
						return await this.ctx.remote.thaliris.diagnostics(sessionId);
					});
					if (!response.ok) throw new Error(remoteError(response));
					this.store.update((state) => {
						state.diagnostics = response.value;
						state.diagnosticStatus = "ready";
					});
					return true;
				} catch (error) {
					this.store.update((state) => {
						state.diagnosticError = describeError(error);
						state.diagnosticStatus = "error";
					});
					return false;
				}
			}
			async approveMemory(sessionId, proposalId) {
				if (this.store.getSnapshot().approvalStatus === "saving") return false;
				this.store.update((state) => {
					state.approvalStatus = "saving";
					state.approvalReceipt = void 0;
					state.approvalError = void 0;
				});
				try {
					const response = await this.ctx.sessions.using(sessionId, { source: "gateway" }, async () => {
						return await this.ctx.remote.thaliris.approveMemory(sessionId, proposalId);
					});
					if (!response.ok) throw new Error(remoteError(response));
					this.store.update((state) => {
						state.approvalReceipt = response.value;
						state.approvalStatus = "ready";
					});
					await this.loadDiagnostics(sessionId);
					return true;
				} catch (error) {
					this.store.update((state) => {
						state.approvalError = describeError(error);
						state.approvalStatus = "error";
					});
					return false;
				}
			}
			async dispose() {
				for (const stop of this.stops) stop();
			}
		};
		//#endregion
		//#region \0dsh-css:C:\Users\12298\Documents\Codex\2026-10-02\codex-benchmark-1-thaliris-host-neutral\work\deepseek-harness\packages\client\thaliris-build-KE6slc\src\client\ThalirisPage.module.css.mjs
		const css = ".m7ZUFa_page{width:100%;color:var(--dsw-alias-text-primary);flex-direction:column;gap:18px;display:flex}.m7ZUFa_header,.m7ZUFa_sectionHead,.m7ZUFa_cardHead,.m7ZUFa_inline,.m7ZUFa_inlineActions,.m7ZUFa_permissionRow{align-items:center;gap:12px;display:flex}.m7ZUFa_header,.m7ZUFa_sectionHead,.m7ZUFa_cardHead{justify-content:space-between}.m7ZUFa_header{align-items:flex-start}.m7ZUFa_title{margin:0;font-size:20px;font-weight:600}.m7ZUFa_summary,.m7ZUFa_section p,.m7ZUFa_section small{color:var(--dsw-alias-text-secondary)}.m7ZUFa_summary{margin:5px 0 0}.m7ZUFa_section{flex-direction:column;gap:14px;min-width:0;display:flex}.m7ZUFa_fieldset{border:0;flex-direction:column;gap:14px;min-width:0;margin:0;padding:0;display:flex}.m7ZUFa_visuallyHidden{clip:rect(0, 0, 0, 0);white-space:nowrap;border:0;width:1px;height:1px;margin:-1px;padding:0;position:absolute;overflow:hidden}.m7ZUFa_section h3,.m7ZUFa_section h4{margin:0;font-weight:600}.m7ZUFa_section h3{font-size:16px}.m7ZUFa_section h4{font-size:14px}.m7ZUFa_section p{margin:0;line-height:1.5}.m7ZUFa_field{flex-direction:column;gap:6px;min-width:0;display:flex}.m7ZUFa_field>span{font-size:13px;font-weight:500}.m7ZUFa_field textarea{resize:vertical;box-sizing:border-box;width:100%;min-height:118px;color:var(--dsw-alias-text-primary);background:var(--dsw-alias-surface-primary);border:1px solid var(--dsw-alias-border-primary);font:inherit;border-radius:8px;padding:10px 12px;line-height:1.5}.m7ZUFa_field select,.m7ZUFa_inline select,.m7ZUFa_section>select{max-width:100%;color:var(--dsw-alias-text-primary);background:var(--dsw-alias-surface-primary);border:1px solid var(--dsw-alias-border-primary);font:inherit;border-radius:8px;padding:8px 10px}.m7ZUFa_inline{flex-wrap:wrap}.m7ZUFa_inline select{flex:1;min-width:220px}.m7ZUFa_inlineActions{flex-wrap:wrap;justify-content:flex-end}.m7ZUFa_grid{grid-template-columns:repeat(auto-fit,minmax(min(100%,250px),1fr));gap:14px;display:grid}.m7ZUFa_wide{grid-column:1/-1}.m7ZUFa_stack{flex-direction:column;gap:10px;display:flex}.m7ZUFa_card{border:1px solid var(--dsw-alias-border-primary);background:var(--dsw-alias-surface-secondary);border-radius:10px;flex-direction:column;gap:12px;min-width:0;padding:14px;display:flex}.m7ZUFa_cardHead{align-items:flex-start}.m7ZUFa_cardHead code,.m7ZUFa_cardHead p{color:var(--dsw-alias-text-secondary);overflow-wrap:anywhere;margin-top:5px;display:block}.m7ZUFa_subsection{flex-direction:column;gap:10px;padding-top:4px;display:flex}.m7ZUFa_checkGrid{grid-template-columns:repeat(auto-fit,minmax(min(100%,280px),1fr));gap:8px 12px;display:grid}.m7ZUFa_permissionRow{flex-wrap:wrap;justify-content:flex-start;padding:7px 0}.m7ZUFa_permissionRow strong{min-width:140px}.m7ZUFa_notice{background:var(--dsw-alias-surface-tertiary);overflow-wrap:anywhere;border-radius:8px;padding:9px 11px}.m7ZUFa_error{color:var(--dsw-alias-text-danger);background:var(--dsw-alias-surface-danger);border-radius:8px;padding:9px 11px}.m7ZUFa_card pre{max-width:100%;max-height:260px;color:var(--dsw-alias-text-primary);background:var(--dsw-alias-surface-primary);white-space:pre-wrap;overflow-wrap:anywhere;border-radius:7px;margin:0;padding:10px;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;overflow:auto}@media (width<=680px){.m7ZUFa_header,.m7ZUFa_sectionHead{flex-direction:column;align-items:flex-start}.m7ZUFa_inline{flex-direction:column;align-items:stretch}.m7ZUFa_inline select{box-sizing:border-box;width:100%}}";
		const tagId = "@thaliris/dsh-plugin/ThalirisPage.module.css";
		if (typeof document !== "undefined" && document.querySelector("style[data-plugin-css=" + JSON.stringify(tagId) + "]") === null) {
			const tag = document.createElement("style");
			tag.dataset.plugin = "@thaliris/dsh-plugin";
			tag.dataset.pluginCss = tagId;
			tag.textContent = css;
			document.head.appendChild(tag);
		}
		var ThalirisPage_module_css_default = {
			"card": "m7ZUFa_card",
			"cardHead": "m7ZUFa_cardHead",
			"checkGrid": "m7ZUFa_checkGrid",
			"error": "m7ZUFa_error",
			"field": "m7ZUFa_field",
			"fieldset": "m7ZUFa_fieldset",
			"grid": "m7ZUFa_grid",
			"header": "m7ZUFa_header",
			"inline": "m7ZUFa_inline",
			"inlineActions": "m7ZUFa_inlineActions",
			"notice": "m7ZUFa_notice",
			"page": "m7ZUFa_page",
			"permissionRow": "m7ZUFa_permissionRow",
			"section": "m7ZUFa_section",
			"sectionHead": "m7ZUFa_sectionHead",
			"stack": "m7ZUFa_stack",
			"subsection": "m7ZUFa_subsection",
			"summary": "m7ZUFa_summary",
			"title": "m7ZUFa_title",
			"visuallyHidden": "m7ZUFa_visuallyHidden",
			"wide": "m7ZUFa_wide"
		};
		//#endregion
		//#region src/client/ThalirisPage.tsx
		const TABS = [
			{
				id: "general",
				key: "tabGeneral"
			},
			{
				id: "roles",
				key: "tabRoles"
			},
			{
				id: "memory",
				key: "tabMemory"
			},
			{
				id: "context",
				key: "tabContext"
			},
			{
				id: "diagnostics",
				key: "tabDiagnostics"
			}
		];
		function json(value) {
			try {
				return JSON.stringify(value, null, 2);
			} catch {
				return String(value);
			}
		}
		function record(value) {
			return typeof value === "object" && value !== null && !Array.isArray(value) ? value : void 0;
		}
		function routeKey(provider, model) {
			return JSON.stringify([provider, model]);
		}
		function exactRouteKey(route) {
			return JSON.stringify([
				route.provider,
				route.model,
				route.reasoningEffort ?? null
			]);
		}
		function routesOf(state) {
			return state.modelCatalog?.groups.flatMap((group) => group.models.map((model) => ({
				provider: group.id,
				providerName: group.name,
				model: model.id,
				modelName: model.name,
				efforts: model.reasoning?.efforts ?? []
			}))) ?? [];
		}
		function roleWith(role, patch) {
			return {
				...role,
				...patch
			};
		}
		function duplicateRole(role, roles) {
			const base = role.id.trim() || "role";
			let id = `${base}-copy`;
			for (let suffix = 2; roles.some((value) => value.id === id); suffix++) id = `${base}-copy-${suffix}`;
			return {
				...structuredClone(role),
				id
			};
		}
		function ThalirisPage(props) {
			const { t } = props;
			const policy = props.usePolicy((state) => state);
			const native = props.useNative((state) => state);
			const [tab, setTab] = (0, react.useState)("general");
			const [templateId, setTemplateId] = (0, react.useState)("");
			const [workspaceId, setWorkspaceId] = (0, react.useState)("");
			const [sessionId, setSessionId] = (0, react.useState)("");
			const [copied, setCopied] = (0, react.useState)(false);
			const headingId = (0, react.useId)();
			const draft = policy.draft;
			const shell = {
				available: policy.available,
				writable: policy.writable,
				dirty: policy.dirty && policy.writable,
				invalid: Boolean(policy.validationError) || policy.conflict,
				saving: policy.saving,
				failed: Boolean(policy.error)
			};
			const tfn = t;
			const templates = native.templates;
			const routeChoices = (0, react.useMemo)(() => routesOf(native), [native.modelCatalog]);
			const edit = (field, value) => props.edit(field, value);
			const editRole = (index, patch) => {
				if (!draft) return;
				edit("roles", draft.roles.map((role, i) => i === index ? roleWith(role, patch) : role));
			};
			const editMemory = (patch) => {
				if (draft) edit("memory", {
					...draft.memory,
					...patch
				});
			};
			if (props.view === "summary") return t("summary");
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: ThalirisPage_module_css_default.page,
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("header", {
						className: ThalirisPage_module_css_default.header,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h2", {
							className: ThalirisPage_module_css_default.title,
							id: headingId,
							children: "Thaliris"
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: ThalirisPage_module_css_default.summary,
							children: t("summary")
						})] }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
							onClick: props.refresh,
							children: t("projectionRefresh")
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.SegmentedTabs, {
						label: t("settingsLabel"),
						value: tab,
						onChange: (value) => setTab(value),
						items: TABS.map((item) => ({
							value: item.id,
							label: t(item.key),
							id: `${headingId}-tab-${item.id}`,
							panelId: `${headingId}-panel`
						}))
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)(_deepseek_ai_dsh_client_ui_primitives.SettingsForm, {
						labels: {
							unavailable: t("formUnavailable"),
							readOnly: t("readOnly"),
							saveFailed: t("saveFailed"),
							save: t("save"),
							saving: t("saving")
						},
						state: shell,
						onSave: props.save,
						onDiscard: props.discard,
						children: [
							policy.conflict ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								className: ThalirisPage_module_css_default.error,
								role: "alert",
								children: t("conflict")
							}) : null,
							policy.validationError ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								className: ThalirisPage_module_css_default.error,
								role: "alert",
								children: policy.validationError
							}) : null,
							policy.error ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
								className: ThalirisPage_module_css_default.error,
								role: "alert",
								children: policy.error
							}) : null,
							policy.available && (!policy.writable || policy.conflict) ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
								onClick: props.discard,
								children: t("discard")
							}) : null,
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("fieldset", {
								className: ThalirisPage_module_css_default.fieldset,
								disabled: !policy.writable,
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("legend", {
										className: ThalirisPage_module_css_default.visuallyHidden,
										children: t("settingsLabel")
									}),
									tab === "general" && draft ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
										className: ThalirisPage_module_css_default.section,
										children: [
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: t("generalTitle") }),
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("generalHelp") }),
											/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
												className: ThalirisPage_module_css_default.field,
												children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("controllerPrompt") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("textarea", {
													value: draft.controllerPrompt,
													onChange: (event) => edit("controllerPrompt", event.currentTarget.value)
												})]
											})
										]
									}) : null,
									tab === "roles" && draft ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
										className: ThalirisPage_module_css_default.section,
										children: [
											/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
												className: ThalirisPage_module_css_default.sectionHead,
												children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: t("rolesTitle") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("rolesHelp") })] }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
													variant: "primary",
													onClick: () => edit("roles", [...draft.roles, {
														id: "",
														name: "",
														description: "",
														prompt: "",
														enabled: true,
														tools: [],
														modelPolicy: {
															mode: "inherit",
															routes: []
														},
														memory: {
															read: [],
															write: []
														},
														context: {
															handoff: true,
															memory: false
														}
													}]),
													children: t("addRole")
												})]
											}),
											native.templateStatus === "idle" || native.templateStatus === "error" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
												onClick: () => props.refresh(),
												children: t("loadTemplates")
											}) : null,
											native.templateStatus === "error" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("templateUnavailable") }) : null,
											templates.length ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
												className: ThalirisPage_module_css_default.inline,
												children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
													value: templateId,
													onChange: (event) => setTemplateId(event.currentTarget.value),
													children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
														value: "",
														children: t("chooseTemplate")
													}), templates.map((template) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
														value: template.id,
														children: template.name
													}, template.id))]
												}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
													disabled: !templateId || draft.roles.some((role) => role.id === templateId),
													onClick: () => {
														const template = templates.find((role) => role.id === templateId);
														if (template) edit("roles", [...draft.roles, structuredClone(template)]);
													},
													children: t("addTemplate")
												})]
											}) : null,
											draft.roles.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noRoles") }) : null,
											draft.roles.map((role, index) => {
												const chosenRoutes = role.modelPolicy.routes;
												const route = chosenRoutes[0];
												const selectedKey = route ? routeKey(route.provider, route.model) : "";
												const selectedChoice = routeChoices.find((candidate) => routeKey(candidate.provider, candidate.model) === selectedKey);
												const routeUnavailable = role.modelPolicy.mode === "fixed" && Boolean(route && !selectedChoice);
												const availableExactRoutes = routeChoices.flatMap((choice) => [{
													...choice,
													reasoningEffort: void 0,
													effortName: t("defaultEffort"),
													available: true
												}, ...choice.efforts.map((effort) => ({
													...choice,
													reasoningEffort: effort.id,
													effortName: effort.name ?? effort.id,
													available: true
												}))]);
												const allowedChoices = [...availableExactRoutes, ...chosenRoutes.filter((value) => !availableExactRoutes.some((choice) => exactRouteKey(choice) === exactRouteKey(value))).map((value) => ({
													...value,
													providerName: value.provider,
													modelName: value.model,
													effortName: value.reasoningEffort ?? t("defaultEffort"),
													available: false
												}))];
												const updateRoute = (key) => {
													const candidate = routeChoices.find((item) => routeKey(item.provider, item.model) === key);
													if (!candidate) return;
													const next = {
														provider: candidate.provider,
														model: candidate.model
													};
													editRole(index, { modelPolicy: {
														...role.modelPolicy,
														routes: role.modelPolicy.mode === "allowed" ? [...role.modelPolicy.routes.filter((item) => routeKey(item.provider, item.model) !== key), next] : [next]
													} });
												};
												return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("article", {
													className: ThalirisPage_module_css_default.card,
													children: [
														/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
															className: ThalirisPage_module_css_default.cardHead,
															children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", { children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: role.name || role.id || t("addRole") }) }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Switch, {
																checked: role.enabled,
																label: `${t("enabled")}: ${role.name || role.id || index + 1}`,
																onChange: (enabled) => editRole(index, { enabled })
															})]
														}),
														/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
															className: ThalirisPage_module_css_default.grid,
															children: [
																/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
																	className: ThalirisPage_module_css_default.field,
																	children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("roleId") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Input, {
																		value: role.id,
																		onChange: (event) => editRole(index, { id: event.currentTarget.value })
																	})]
																}),
																/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
																	className: ThalirisPage_module_css_default.field,
																	children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("roleName") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Input, {
																		value: role.name,
																		onChange: (event) => editRole(index, { name: event.currentTarget.value })
																	})]
																}),
																/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
																	className: `${ThalirisPage_module_css_default.field} ${ThalirisPage_module_css_default.wide}`,
																	children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("roleDescription") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Input, {
																		value: role.description,
																		onChange: (event) => editRole(index, { description: event.currentTarget.value })
																	})]
																})
															]
														}),
														/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
															className: ThalirisPage_module_css_default.field,
															children: [
																/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("rolePrompt") }),
																/* @__PURE__ */ (0, react_jsx_runtime.jsx)("textarea", {
																	"aria-label": t("rolePrompt"),
																	value: role.prompt,
																	onChange: (event) => editRole(index, { prompt: event.currentTarget.value })
																}),
																/* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: t("rolePromptHelp") })
															]
														}),
														/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
															className: ThalirisPage_module_css_default.subsection,
															children: [
																/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("modelPolicy") }),
																/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
																	className: ThalirisPage_module_css_default.field,
																	children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("modelPolicy") }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
																		value: role.modelPolicy.mode,
																		onChange: (event) => editRole(index, { modelPolicy: {
																			...role.modelPolicy,
																			mode: event.currentTarget.value,
																			routes: event.currentTarget.value === "inherit" ? [] : role.modelPolicy.routes
																		} }),
																		children: [
																			/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
																				value: "inherit",
																				children: t("inherit")
																			}),
																			/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
																				value: "fixed",
																				children: t("fixed")
																			}),
																			/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
																				value: "allowed",
																				children: t("allowed")
																			})
																		]
																	})]
																}),
																role.modelPolicy.mode !== "inherit" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
																	native.modelStatus === "loading" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("modelCatalogLoading") }) : null,
																	native.modelStatus !== "ready" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("modelCatalogUnavailable") }) : null,
																	routeUnavailable ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
																		className: ThalirisPage_module_css_default.notice,
																		children: [
																			t("unavailableRoute"),
																			": ",
																			route?.provider,
																			"/",
																			route?.model
																		]
																	}) : null,
																	role.modelPolicy.mode === "fixed" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
																		className: ThalirisPage_module_css_default.field,
																		children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("selectedModel") }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
																			value: selectedKey,
																			onChange: (event) => updateRoute(event.currentTarget.value),
																			children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
																				value: "",
																				children: t("noModels")
																			}), routeChoices.map((item) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("option", {
																				value: routeKey(item.provider, item.model),
																				children: [
																					item.providerName,
																					" / ",
																					item.modelName
																				]
																			}, routeKey(item.provider, item.model)))]
																		})]
																	}) : null,
																	role.modelPolicy.mode === "allowed" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
																		className: ThalirisPage_module_css_default.checkGrid,
																		children: allowedChoices.map((item) => {
																			const key = exactRouteKey(item);
																			const checked = role.modelPolicy.routes.some((value) => exactRouteKey(value) === key);
																			return /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
																				className: ThalirisPage_module_css_default.stack,
																				children: /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
																					checked,
																					label: item.available ? `${item.providerName} / ${item.modelName} (${item.effortName})` : `${item.provider}/${item.model} (${item.effortName}) — ${t("unavailableRoute")}`,
																					onChange: (next) => {
																						const selected = role.modelPolicy.routes.filter((value) => exactRouteKey(value) !== key);
																						if (next && item.available) selected.push({
																							provider: item.provider,
																							model: item.model,
																							...item.reasoningEffort ? { reasoningEffort: item.reasoningEffort } : {}
																						});
																						editRole(index, { modelPolicy: {
																							...role.modelPolicy,
																							routes: selected
																						} });
																					}
																				})
																			}, key);
																		})
																	}) : null,
																	role.modelPolicy.mode === "fixed" && selectedChoice?.efforts.length ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
																		className: ThalirisPage_module_css_default.field,
																		children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("reasoningEffort") }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
																			value: route?.reasoningEffort ?? "",
																			onChange: (event) => {
																				if (!route) return;
																				const next = {
																					provider: route.provider,
																					model: route.model,
																					...event.currentTarget.value ? { reasoningEffort: event.currentTarget.value } : {}
																				};
																				editRole(index, { modelPolicy: {
																					...role.modelPolicy,
																					routes: [next]
																				} });
																			},
																			children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
																				value: "",
																				children: t("defaultEffort")
																			}), selectedChoice.efforts.map((effort) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
																				value: effort.id,
																				children: effort.name ?? effort.id
																			}, effort.id))]
																		})]
																	}) : null
																] }) : null
															]
														}),
														/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
															className: ThalirisPage_module_css_default.subsection,
															children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("tools") }), native.toolStatus !== "ready" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("toolsUnavailable") }), role.tools.map((name) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
																checked: true,
																label: `${name} — ${t("toolUnavailable")}`,
																onChange: (checked) => {
																	if (!checked) editRole(index, { tools: role.tools.filter((value) => value !== name) });
																}
															}, name))] }) : native.tools.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noTools") }), role.tools.map((name) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
																checked: true,
																label: `${name} — ${t("toolUnavailable")}`,
																onChange: (checked) => {
																	if (!checked) editRole(index, { tools: role.tools.filter((value) => value !== name) });
																}
															}, name))] }) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
																className: ThalirisPage_module_css_default.checkGrid,
																children: [...new Set([...native.tools.filter((tool) => !tool.name.startsWith("thaliris_task_") && tool.name !== "thaliris_reconcile" && tool.name !== "thaliris_workstream").map((tool) => tool.name), ...role.tools])].map((name) => {
																	const tool = native.tools.find((item) => item.name === name);
																	const reserved = name.startsWith("thaliris_task_") || name === "thaliris_reconcile" || name === "thaliris_workstream";
																	return /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
																		checked: role.tools.includes(name),
																		disabled: reserved && !role.tools.includes(name),
																		label: `${name}${tool?.description ? ` — ${tool.description}` : ` — ${t("toolUnavailable")}`}`,
																		onChange: (checked) => {
																			const tools = role.tools.filter((value) => value !== name);
																			if (checked) tools.push(name);
																			editRole(index, { tools });
																		}
																	}, name);
																})
															})]
														}),
														/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
															className: ThalirisPage_module_css_default.inlineActions,
															children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
																onClick: () => {
																	const duplicate = duplicateRole(role, draft.roles);
																	edit("roles", [
																		...draft.roles.slice(0, index + 1),
																		duplicate,
																		...draft.roles.slice(index + 1)
																	]);
																},
																children: t("duplicateRole")
															}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
																onClick: () => edit("roles", draft.roles.filter((_, i) => i !== index)),
																children: t("deleteRole")
															})]
														}),
														/* @__PURE__ */ (0, react_jsx_runtime.jsx)(RoleGrantControls, {
															role,
															index,
															providers: native.providers,
															t: tfn,
															onRole: editRole
														})
													]
												}, `${role.id || "draft"}-${index}`);
											})
										]
									}) : null,
									tab === "memory" && draft ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(MemoryFields, {
										draft,
										native,
										t: tfn,
										editMemory,
										openPlugin: props.openPlugin,
										editRole
									}) : null,
									tab === "context" && draft ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
										className: ThalirisPage_module_css_default.section,
										children: [
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: t("contextTitle") }),
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("contextHelp") }),
											/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
												className: ThalirisPage_module_css_default.inline,
												children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
													value: workspaceId,
													onChange: (event) => setWorkspaceId(event.currentTarget.value),
													children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
														value: "",
														children: native.workspaces.phase === "pending" ? t("workspaceLoading") : t("chooseWorkspace")
													}), native.workspaces.items.map((workspace) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("option", {
														value: workspace.workspaceId,
														children: [
															workspace.title,
															" — ",
															workspace.path
														]
													}, workspace.workspaceId))]
												}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
													disabled: !workspaceId || draft.workspaces.some((row) => row.workspaceId === workspaceId),
													onClick: () => {
														const workspace = native.workspaces.items.find((row) => row.workspaceId === workspaceId);
														if (workspace) edit("workspaces", [...draft.workspaces, {
															workspaceId: workspace.workspaceId,
															root: workspace.path,
															enabled: true
														}]);
													},
													children: t("bindWorkspace")
												})]
											}),
											!native.workspaces.items.length && native.workspaces.phase === "ready" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noWorkspaces") }) : null,
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("div", {
												className: ThalirisPage_module_css_default.stack,
												children: draft.workspaces.map((binding, index) => {
													const workspace = native.workspaces.items.find((row) => row.workspaceId === binding.workspaceId);
													return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
														className: ThalirisPage_module_css_default.card,
														children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
															className: ThalirisPage_module_css_default.cardHead,
															children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", { children: [
																/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: workspace?.title ?? binding.workspaceId }),
																/* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", { children: binding.root }),
																!workspace ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
																	className: ThalirisPage_module_css_default.notice,
																	children: t("workspaceMissing")
																}) : null
															] }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Switch, {
																checked: binding.enabled,
																label: `${t("workspaceEnabled")}: ${binding.workspaceId}`,
																onChange: (enabled) => {
																	const workspaces = [...draft.workspaces];
																	workspaces[index] = {
																		...binding,
																		enabled
																	};
																	edit("workspaces", workspaces);
																}
															})]
														}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
															onClick: () => edit("workspaces", draft.workspaces.filter((_, i) => i !== index)),
															children: t("removeWorkspace")
														})]
													}, binding.workspaceId);
												})
											}),
											/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: t("roleHandoff") }),
											draft.roles.map((role, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
												className: ThalirisPage_module_css_default.permissionRow,
												children: [
													/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: role.name || role.id || `Role ${index + 1}` }),
													/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
														checked: role.context.handoff,
														label: t("roleHandoff"),
														onChange: (checked) => editRole(index, { context: {
															...role.context,
															handoff: checked
														} })
													}),
													/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
														checked: role.context.memory,
														label: t("roleMemoryContext"),
														onChange: (checked) => editRole(index, { context: {
															...role.context,
															memory: checked
														} })
													})
												]
											}, role.id || index))
										]
									}) : null
								]
							}),
							tab === "diagnostics" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(Diagnostics, {
								native,
								selectedSession: sessionId,
								setSelectedSession: setSessionId,
								copied,
								setCopied,
								t: tfn,
								loadDiagnostics: () => sessionId && props.loadDiagnostics(sessionId),
								openSession: props.openSession,
								approveMemory: props.approveMemory
							}) : null
						]
					})
				]
			});
		}
		function RoleGrantControls({ role, index, providers, t, onRole }) {
			const providerIds = [...new Set([
				...providers.map((provider) => provider.id),
				...role.memory.read,
				...role.memory.write
			])];
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
				className: ThalirisPage_module_css_default.subsection,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("roleMemory") }), providerIds.map((id) => {
					const provider = providers.find((value) => value.id === id);
					const name = provider?.name ?? id;
					return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: ThalirisPage_module_css_default.permissionRow,
						children: [
							/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("strong", { children: [
								name,
								" (",
								id,
								")"
							] }),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
								checked: role.memory.read.includes(id),
								label: `${t("roleRead")}: ${name}`,
								onChange: (checked) => {
									const read = role.memory.read.filter((value) => value !== id);
									if (checked) read.push(id);
									onRole(index, { memory: {
										...role.memory,
										read
									} });
								}
							}),
							/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
								checked: role.memory.write.includes(id),
								label: `${t("roleWrite")}: ${name}`,
								onChange: (checked) => {
									const write = role.memory.write.filter((value) => value !== id);
									if (checked) write.push(id);
									onRole(index, { memory: {
										...role.memory,
										write
									} });
								}
							}),
							provider ? null : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
								className: ThalirisPage_module_css_default.notice,
								children: [
									t("providerMissing"),
									": ",
									id
								]
							})
						]
					}, id);
				})]
			});
		}
		function MemoryFields({ draft, native, t, editMemory, openPlugin, editRole }) {
			const memory = draft.memory;
			const toggle = (field, id, checked) => {
				const values = memory[field].filter((value) => value !== id);
				if (checked) values.push(id);
				editMemory({ [field]: values });
			};
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
				className: ThalirisPage_module_css_default.section,
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: t("memoryTitle") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("memoryHelp") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("label", {
						className: ThalirisPage_module_css_default.field,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("span", { children: t("memoryMode") }), /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
							value: memory.mode,
							onChange: (event) => editMemory({ mode: event.currentTarget.value }),
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "disabled",
									children: t("modeDisabled")
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "manual",
									children: t("modeManual")
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "suggest-review",
									children: t("modeSuggest")
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
									value: "auto",
									children: t("modeAuto")
								})
							]
						})]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: ThalirisPage_module_css_default.permissionRow,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
							checked: memory.autoAuthorized,
							label: t("autoAuthorized"),
							onChange: (autoAuthorized) => editMemory({ autoAuthorized })
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("small", { children: t("autoAuthorizedHelp") })]
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("providers") }),
					native.providers.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noProviders") }) : null,
					[...new Set([
						...native.providers.map((provider) => provider.id),
						...memory.providers,
						...memory.controllerRead,
						...memory.controllerWrite
					])].map((id) => {
						const provider = native.providers.find((value) => value.id === id);
						const name = provider?.name ?? id;
						return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							className: ThalirisPage_module_css_default.permissionRow,
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
									checked: memory.providers.includes(id),
									label: `${name} (${id}) — ${t("providerEnabled")}`,
									onChange: (checked) => toggle("providers", id, checked)
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
									checked: memory.controllerRead.includes(id),
									label: `${t("controllerRead")}: ${name}`,
									onChange: (checked) => toggle("controllerRead", id, checked)
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Checkbox, {
									checked: memory.controllerWrite.includes(id),
									label: `${t("controllerWrite")}: ${name}`,
									onChange: (checked) => toggle("controllerWrite", id, checked)
								}),
								provider ? null : /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", {
									className: ThalirisPage_module_css_default.notice,
									children: [
										t("providerMissing"),
										": ",
										id
									]
								})
							]
						}, id);
					}),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: ThalirisPage_module_css_default.inlineActions,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
							onClick: () => openPlugin("@thaliris/dsh-memory"),
							children: t("openMemoryPlugin")
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
							onClick: () => openPlugin("@thaliris/dsh-memory-local"),
							children: t("openLocalPlugin")
						})]
					}),
					draft.roles.map((role, index) => /* @__PURE__ */ (0, react_jsx_runtime.jsx)(RoleGrantControls, {
						role,
						index,
						providers: native.providers,
						t,
						onRole: editRole
					}, `${role.id || "draft"}-${index}`))
				]
			});
		}
		function Diagnostics({ native, selectedSession, setSelectedSession, copied, setCopied, t, loadDiagnostics, openSession, approveMemory }) {
			const roots = native.sessions.ids.map((id) => native.sessions.byId[id]).filter((row) => row && row.parentId === void 0 && row.origin !== "subagent");
			const data = record(native.diagnostics);
			const task = record(data?.task);
			const taskState = record(task?.state);
			const pendingResults = (taskState?.pending_results ?? []).flatMap((item) => {
				try {
					return [typeof item === "string" ? JSON.parse(item) : item];
				} catch {
					return [];
				}
			}).map(record).filter((item) => item);
			const proposals = pendingResults.filter((item) => typeof item.proposal_id === "string" && typeof item.approval_id !== "string" && typeof item.provider === "string" && typeof item.key === "string" && typeof item.text === "string" && item.provenance !== void 0);
			const approvalReceipts = pendingResults.filter((item) => typeof item.approval_id === "string" && typeof item.proposal_id === "string");
			const reservations = Array.isArray(data?.reservations) ? data.reservations : [];
			const approved = new Set(approvalReceipts.map((value) => value.proposal_id));
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("section", {
				className: ThalirisPage_module_css_default.section,
				children: [
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h3", { children: t("diagnosticsTitle") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("diagnosticsHelp") }),
					/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
						className: ThalirisPage_module_css_default.inline,
						children: [/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("select", {
							value: selectedSession,
							onChange: (event) => setSelectedSession(event.currentTarget.value),
							children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("option", {
								value: "",
								children: t("selectSession")
							}), roots.map((row) => /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("option", {
								value: row.id,
								children: [
									row.displayTitle,
									" — ",
									row.id
								]
							}, row.id))]
						}), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
							disabled: !selectedSession || native.diagnosticStatus === "loading",
							onClick: loadDiagnostics,
							children: native.diagnosticStatus === "loading" ? t("diagnosticsLoading") : native.diagnosticStatus === "ready" ? t("refreshDiagnostics") : t("loadDiagnostics")
						})]
					}),
					roots.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noRootSessions") }) : null,
					native.diagnosticStatus === "error" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
						className: ThalirisPage_module_css_default.error,
						children: native.diagnosticError ?? t("diagnosticsUnavailable")
					}) : null,
					data ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [
						/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
							className: ThalirisPage_module_css_default.grid,
							children: [
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(InfoCard, {
									title: t("taskEvidence"),
									value: task
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(InfoCard, {
									title: t("workspaceEvidence"),
									value: data.workspace
								}),
								/* @__PURE__ */ (0, react_jsx_runtime.jsx)(InfoCard, {
									title: t("permissionsEvidence"),
									value: {
										permissions: data.permissions,
										providers: data.providers
									}
								})
							]
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("reservationEvidence") }),
						reservations.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noReservations") }) : reservations.map((item, index) => {
							const row = record(item) ?? {};
							const reservation = record(row.reservation) ?? {};
							const observation = record(row.native) ?? {};
							const outcome = observation.outcome;
							const terminal = [
								"completed",
								"aborted",
								"error",
								"max-tokens",
								"blocked",
								"interrupted"
							].includes(String(outcome));
							const resident = typeof observation.reason === "string" && observation.reason.includes("resident");
							const action = terminal ? "reconcile" : resident ? "cancel-reconcile" : "check";
							const args = {
								task_id: taskState?.task_id,
								base_revision: taskState?.revision,
								action
							};
							const copy = async () => {
								try {
									await navigator.clipboard.writeText(json(args));
									setCopied(true);
								} catch {
									setCopied(false);
								}
							};
							return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("article", {
								className: ThalirisPage_module_css_default.card,
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: reservation.workstream ?? reservation.correlation ?? t("reservationEvidence") }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: [
										t("outcome"),
										": ",
										String(outcome ?? "UNKNOWN")
									] }),
									!terminal ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
										className: ThalirisPage_module_css_default.notice,
										children: t("unknownOutcome")
									}) : null,
									observation.child_id ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("div", {
										className: ThalirisPage_module_css_default.inline,
										children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("code", { children: String(observation.child_id) }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
											onClick: () => openSession(String(observation.child_id)),
											children: t("openChildSession")
										})]
									}) : null,
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("reconcileGuide") }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("details", { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("summary", { children: t("reconcileCommand") }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: json(args) })] }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
										onClick: () => {
											copy();
										},
										children: copied ? t("commandCopied") : t("copyCommand")
									})
								]
							}, `${reservation.workstream ?? "reservation"}-${index}`);
						}),
						/* @__PURE__ */ (0, react_jsx_runtime.jsx)("h4", { children: t("proposals") }),
						proposals.length === 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("noProposals") }) : proposals.map((proposal) => {
							const memory = record(data.permissions)?.memory;
							const canApprove = memory && memory.mode !== "disabled" && memory.providers?.includes(proposal.provider) && memory.controllerWrite?.includes(proposal.provider);
							return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("article", {
								className: ThalirisPage_module_css_default.card,
								children: [
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: proposal.proposal_id }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: [
										t("proposalProvider"),
										": ",
										proposal.provider
									] }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: [
										t("proposalKey"),
										": ",
										proposal.key
									] }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("proposalText") }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: String(proposal.text ?? "") }),
									/* @__PURE__ */ (0, react_jsx_runtime.jsxs)("p", { children: [
										t("proposalProvenance"),
										": ",
										json(proposal.provenance)
									] }),
									approved.has(proposal.proposal_id) ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", { children: t("alreadyApproved") }) : canApprove ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(_deepseek_ai_dsh_client_ui_primitives.Button, {
										variant: "primary",
										disabled: native.approvalStatus === "saving",
										onClick: () => approveMemory(selectedSession, proposal.proposal_id),
										children: t("approveProposal")
									}) : /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
										className: ThalirisPage_module_css_default.notice,
										children: t("noApprovalGrant")
									})
								]
							}, proposal.proposal_id);
						}),
						approvalReceipts.length > 0 ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(InfoCard, {
							title: t("approvalReceipts"),
							value: approvalReceipts
						}) : null,
						native.approvalStatus === "ready" ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)(InfoCard, {
							title: t("proposalApproved"),
							value: native.approvalReceipt
						}) : null,
						native.approvalStatus === "error" ? /* @__PURE__ */ (0, react_jsx_runtime.jsxs)(react_jsx_runtime.Fragment, { children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: ThalirisPage_module_css_default.error,
							children: native.approvalError ?? t("approvalUncertain")
						}), native.approvalError ? /* @__PURE__ */ (0, react_jsx_runtime.jsx)("p", {
							className: ThalirisPage_module_css_default.notice,
							children: t("approvalUncertain")
						}) : null] }) : null
					] }) : null
				]
			});
		}
		function InfoCard({ title, value }) {
			return /* @__PURE__ */ (0, react_jsx_runtime.jsxs)("article", {
				className: ThalirisPage_module_css_default.card,
				children: [/* @__PURE__ */ (0, react_jsx_runtime.jsx)("strong", { children: title }), /* @__PURE__ */ (0, react_jsx_runtime.jsx)("pre", { children: json(value) })]
			});
		}
		//#endregion
		//#region src/client/locales.ts
		/** Web/Desktop settings strings for the shared Thaliris client. */
		const NS = "settings.thaliris";
		const en = {
			summary: "Edit Thaliris guidance, roles, Workspace access, memory grants, and native runtime observations.",
			settingsLabel: "Thaliris settings",
			tabGeneral: "General",
			tabRoles: "Roles",
			tabMemory: "Memory",
			tabContext: "Context",
			tabDiagnostics: "Diagnostics",
			formUnavailable: "Thaliris settings are not available from this connection.",
			readOnly: "This connection cannot persist Settings. Changes stay unavailable until the Host serves writable Settings.",
			save: "Save changes",
			saving: "Saving…",
			saveFailed: "The Host did not accept these Settings.",
			discard: "Reload native values",
			conflict: "Settings changed after these edits began. Reload native values before editing again.",
			generalTitle: "Controller guidance",
			generalHelp: "This visible prompt is sent to the native root Controller in a configured Workspace. Thaliris records its decisions but does not make them.",
			controllerPrompt: "Controller guidance",
			rolesTitle: "Editable roles",
			rolesHelp: "Role records are user policy. The Controller chooses which enabled role, if any, fits each bounded Workstream.",
			addRole: "New role",
			noRoles: "No roles are stored. Use New role or add an explicit template.",
			addTemplate: "Add selected template",
			chooseTemplate: "Choose a template",
			loadTemplates: "Load templates",
			templateUnavailable: "Templates are unavailable while the runtime API is not mounted.",
			duplicateRole: "Duplicate",
			deleteRole: "Delete",
			enabled: "Enabled",
			roleId: "Stable role ID",
			roleName: "Name",
			roleDescription: "Description",
			rolePrompt: "Full role prompt",
			rolePromptHelp: "This complete prompt is sent to the selected native child. No hidden role suffix is added.",
			tools: "Allowed native tools",
			toolsUnavailable: "The native tool list is unavailable. Retry after enabling the runtime API.",
			refresh: "Refresh",
			noTools: "No native tools were returned.",
			toolUnavailable: "not in the current native tool catalog",
			modelPolicy: "Model policy",
			inherit: "Inherit the native parent model",
			fixed: "Use one fixed route",
			allowed: "Allow these exact routes",
			modelCatalogUnavailable: "The native model catalog is unavailable.",
			modelCatalogLoading: "Loading the native model catalog…",
			noModels: "The native catalog has no available routes.",
			selectedModel: "Selected route",
			reasoningEffort: "Reasoning effort",
			defaultEffort: "Native default",
			unavailableRoute: "Stored route is no longer in the native catalog",
			memoryTitle: "Memory policy",
			memoryHelp: "Memory stays disabled until providers and explicit grants are selected. Auto writes also need a separate persisted user opt-in.",
			memoryMode: "Write policy",
			modeDisabled: "Disabled",
			modeManual: "Manual",
			modeSuggest: "Suggest and review",
			modeAuto: "Automatic writes",
			autoAuthorized: "I explicitly authorize automatic memory writes",
			autoAuthorizedHelp: "This consent is independent from the selected write policy.",
			providers: "Available providers",
			providerEnabled: "Enabled for Thaliris",
			providerMissing: "Selected provider is not installed or currently unavailable",
			noProviders: "No memory provider is active. Install an optional provider through the native Plugins page.",
			memoryCapabilityMissing: "The memory capability is not active. Install it from the native Plugins page.",
			openMemoryPlugin: "Open memory capability in Plugins",
			openLocalPlugin: "Open local provider in Plugins",
			controllerRead: "Controller may read",
			controllerWrite: "Controller may write or approve proposals",
			roleMemory: "Role memory grants",
			roleRead: "May read",
			roleWrite: "May write or propose",
			contextTitle: "Workspace and role context",
			contextHelp: "Workspace IDs and roots come from the native Workspace list. A matching path alone does not establish a Controller.",
			workspaceBindings: "Bound native Workspaces",
			workspaceLoading: "Loading native Workspaces…",
			noWorkspaces: "No native Workspaces are available.",
			chooseWorkspace: "Choose a native Workspace",
			bindWorkspace: "Bind Workspace",
			removeWorkspace: "Remove binding",
			workspaceEnabled: "Enabled for Thaliris",
			workspaceMissing: "This stored Workspace is not in the current native Workspace list.",
			roleHandoff: "May receive a bounded Controller handoff",
			roleMemoryContext: "May receive explicitly selected memory context",
			diagnosticsTitle: "Native diagnostics",
			diagnosticsHelp: "Select a native root Session. Diagnostics resumes it through native Session services, then verifies the exact Session, Workspace, and Thaliris anchor.",
			selectSession: "Native root Session",
			noRootSessions: "No native root Sessions are listed.",
			loadDiagnostics: "Load diagnostics",
			refreshDiagnostics: "Refresh diagnostics",
			diagnosticsLoading: "Reading current Core and native Session evidence…",
			diagnosticsUnavailable: "Diagnostics are unavailable. Enable the runtime and its native API plugin, then retry.",
			taskEvidence: "Core task evidence",
			workspaceEvidence: "Verified Workspace",
			permissionsEvidence: "Current grants",
			reservationEvidence: "Native reservation evidence",
			noReservations: "No active reservations are listed.",
			outcome: "Native outcome",
			unknownOutcome: "UNKNOWN — the reservation remains reserved.",
			reconcileGuide: "Only a proven native terminal outcome can be reconciled. The native tool records that observation; semantic acceptance remains the Controller’s decision.",
			reconcileCommand: "Native reconcile command arguments",
			copyCommand: "Copy arguments",
			commandCopied: "Arguments copied.",
			childSession: "Observed native child Session",
			openChildSession: "Open child Session",
			proposals: "Memory proposals for review",
			noProposals: "No pending memory proposals were returned.",
			proposalProvider: "Provider",
			proposalKey: "Key",
			proposalText: "Proposed text",
			proposalProvenance: "Provenance",
			approveProposal: "Approve this proposal",
			proposalApproved: "Native provider result and Core approval receipt",
			approvalReceipts: "Recorded Core approval receipts",
			approvalUncertain: "Approval did not return a complete receipt. The provider write may have succeeded; refresh diagnostics and provider state before retrying.",
			alreadyApproved: "An approval receipt is recorded for this proposal.",
			noApprovalGrant: "Approval is unavailable under the current provider, write grant, or memory policy.",
			installForProvider: "Install or enable this provider in the native Plugins page.",
			projectionRefresh: "Refresh native projections",
			runtimeRequiresSetup: "The runtime and API are installed as separate native entries. Configure Python, Core, authority directory, and Workspace access in the native plugin configuration, then enable both entries in Plugins."
		};
		const zh = {
			summary: "编辑 Thaliris 指引、角色、工作区访问、记忆授权和原生运行时观测。",
			settingsLabel: "Thaliris 设置",
			tabGeneral: "常规",
			tabRoles: "角色",
			tabMemory: "记忆",
			tabContext: "上下文",
			tabDiagnostics: "诊断",
			formUnavailable: "此连接无法访问 Thaliris 设置。",
			readOnly: "此连接无法保存设置。只有主机提供可写设置后才能保存。",
			save: "保存更改",
			saving: "正在保存…",
			saveFailed: "主机未接受这些设置。",
			discard: "重新载入原生值",
			conflict: "开始编辑后设置已有变化。请重新载入原生值再编辑。",
			generalTitle: "控制器指引",
			generalHelp: "此处可见的提示会发送给已配置工作区中的原生根控制器。Thaliris 记录决定，但不会代替控制器做决定。",
			controllerPrompt: "控制器指引",
			rolesTitle: "可编辑角色",
			rolesHelp: "角色记录属于用户策略。控制器为每个有界工作流选择合适的已启用角色，也可以不委派。",
			addRole: "新建角色",
			noRoles: "尚未保存角色。可新建角色或显式添加模板。",
			addTemplate: "添加所选模板",
			chooseTemplate: "选择模板",
			loadTemplates: "载入模板",
			templateUnavailable: "运行时 API 未挂载时无法取得模板。",
			duplicateRole: "复制",
			deleteRole: "删除",
			enabled: "已启用",
			roleId: "稳定角色 ID",
			roleName: "名称",
			roleDescription: "说明",
			rolePrompt: "完整角色提示",
			rolePromptHelp: "选择此角色后，完整提示会发送给原生子会话；运行时不会追加隐藏后缀。",
			tools: "允许的原生工具",
			toolsUnavailable: "无法取得原生工具列表。启用运行时 API 后重试。",
			refresh: "刷新",
			noTools: "原生注册表未返回工具。",
			toolUnavailable: "不在当前原生工具目录中",
			modelPolicy: "模型策略",
			inherit: "继承原生父会话模型",
			fixed: "使用一个固定路由",
			allowed: "允许这些精确路由",
			modelCatalogUnavailable: "无法取得原生模型目录。",
			modelCatalogLoading: "正在载入原生模型目录…",
			noModels: "原生目录没有可用路由。",
			selectedModel: "所选路由",
			reasoningEffort: "推理力度",
			defaultEffort: "原生默认值",
			unavailableRoute: "已保存路由已不在原生模型目录中",
			memoryTitle: "记忆策略",
			memoryHelp: "只有选择提供方并设置明确授权后，才能启用记忆。自动写入还需要单独保存的用户授权。",
			memoryMode: "写入策略",
			modeDisabled: "关闭",
			modeManual: "手动",
			modeSuggest: "建议并审核",
			modeAuto: "自动写入",
			autoAuthorized: "我明确授权自动写入记忆",
			autoAuthorizedHelp: "此授权与所选写入策略相互独立。",
			providers: "可用提供方",
			providerEnabled: "为 Thaliris 启用",
			providerMissing: "所选提供方未安装或当前不可用",
			noProviders: "当前没有启用记忆提供方。请从原生插件页面安装可选提供方。",
			memoryCapabilityMissing: "记忆能力未启用。请从原生插件页面安装。",
			openMemoryPlugin: "在插件页打开记忆能力",
			openLocalPlugin: "在插件页打开本地提供方",
			controllerRead: "控制器可读取",
			controllerWrite: "控制器可写入或批准建议",
			roleMemory: "角色记忆授权",
			roleRead: "可读取",
			roleWrite: "可写入或建议",
			contextTitle: "工作区和角色上下文",
			contextHelp: "工作区 ID 和根目录来自原生工作区列表。路径匹配本身不能证明控制器身份。",
			workspaceBindings: "绑定的原生工作区",
			workspaceLoading: "正在载入原生工作区…",
			noWorkspaces: "没有可用的原生工作区。",
			chooseWorkspace: "选择原生工作区",
			bindWorkspace: "绑定工作区",
			removeWorkspace: "移除绑定",
			workspaceEnabled: "为 Thaliris 启用",
			workspaceMissing: "此保存的工作区不在当前原生工作区列表中。",
			roleHandoff: "可接收控制器的有界委派",
			roleMemoryContext: "可接收明确选择的记忆上下文",
			diagnosticsTitle: "原生诊断",
			diagnosticsHelp: "选择原生根会话。诊断会通过原生会话服务恢复会话，然后核实会话、工作区和 Thaliris 锚点。",
			selectSession: "原生根会话",
			noRootSessions: "原生列表中没有根会话。",
			loadDiagnostics: "载入诊断",
			refreshDiagnostics: "刷新诊断",
			diagnosticsLoading: "正在读取当前 Core 和原生会话证据…",
			diagnosticsUnavailable: "无法取得诊断。请启用运行时及原生 API 插件后重试。",
			taskEvidence: "Core 任务证据",
			workspaceEvidence: "已核实工作区",
			permissionsEvidence: "当前授权",
			reservationEvidence: "原生保留记录证据",
			noReservations: "没有活动保留记录。",
			outcome: "原生结果",
			unknownOutcome: "UNKNOWN — 保留记录仍保持保留状态。",
			reconcileGuide: "只有已证明的原生终止结果才能协调。原生工具记录该观测；语义验收仍由控制器决定。",
			reconcileCommand: "原生协调工具参数",
			copyCommand: "复制参数",
			commandCopied: "参数已复制。",
			childSession: "观测到的原生子会话",
			openChildSession: "打开子会话",
			proposals: "待审核记忆建议",
			noProposals: "没有待审核的记忆建议。",
			proposalProvider: "提供方",
			proposalKey: "键",
			proposalText: "建议文本",
			proposalProvenance: "来源",
			approveProposal: "批准此建议",
			proposalApproved: "原生提供方结果和 Core 批准回执",
			approvalReceipts: "已记录的 Core 批准回执",
			approvalUncertain: "批准操作未返回完整回执。提供方写入可能已成功；重试前请刷新诊断和提供方状态。",
			alreadyApproved: "此建议已有批准回执。",
			noApprovalGrant: "当前提供方、写入授权或记忆策略不允许批准。",
			installForProvider: "请在原生插件页安装或启用此提供方。",
			projectionRefresh: "刷新原生投影",
			runtimeRequiresSetup: "运行时和 API 是独立的原生条目。请在原生插件配置中设置 Python、Core、授权目录和工作区访问，然后在插件页启用两个条目。"
		};
		//#endregion
		//#region src/client/index.tsx
		const inject = [
			"slots",
			"locale",
			"remote",
			"remote.session",
			"sessions",
			"workspaces",
			"uiWorkspace",
			"pluginNavigation",
			"configForms"
		];
		/** Mount the same product page in the shared Web client used by Desktop. */
		function apply(ctx) {
			ctx.effect(() => ctx.locale.register(NS, {
				zh,
				en
			}), "thaliris-client: dictionaries");
			const policy = new PolicyEditorController(ctx.configForms.get("thaliris"));
			const native = new NativeProjectionController(ctx);
			const face = {
				hooks: {
					policy: policy.store,
					native: native.store
				},
				edit: policy.edit.bind(policy),
				save: () => {
					policy.save();
				},
				discard: () => policy.discard(),
				refresh: () => {
					native.refresh();
				},
				loadDiagnostics: (sessionId) => {
					native.loadDiagnostics(sessionId);
				},
				approveMemory: (sessionId, proposalId) => {
					native.approveMemory(sessionId, proposalId);
				},
				openPlugin: (packageName) => ctx.pluginNavigation.openBundle(packageName),
				openSession: (sessionId) => ctx.uiWorkspace.openSession(sessionId)
			};
			ctx.effect(() => async () => {
				await Promise.all([policy.dispose(), native.dispose()]);
			}, "thaliris-client: native projection subscriptions");
			ctx.effect(() => ctx.remote.$mount(remoteContribution).then((dispose) => {
				native.refresh();
				return dispose;
			}), "thaliris-client: native Gateway contribution");
			ctx.effect(() => ctx.configForms.whileServed(["thaliris"], () => ctx.slots.inject("plugins.item", () => ctx.slots.register({
				name: "plugins.item",
				id: "thaliris",
				order: 40,
				label: () => ctx.locale.bind(NS)("tabGeneral"),
				locale: NS,
				inject: () => face
			}, ThalirisPage))), "thaliris-client: shared settings page");
		}
		//#endregion
		exports.apply = apply;
		exports.inject = inject;
		return module.exports;
	}
});

//# sourceMappingURL=client.js.map