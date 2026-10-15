import { i as e, t } from "./chunk-KszRVpJ5.js";
//#region ../node_modules/.pnpm/path-is-absolute@1.0.1/node_modules/path-is-absolute/index.js
var n = /* @__PURE__ */ t(((e, t) => {
	function n(e) {
		return e.charAt(0) === "/";
	}
	function r(e) {
		var t = /^([a-zA-Z]:|[\\\/]{2}[^\\\/]+[\\\/]+[^\\\/]+)?([\\\/])?([\s\S]*?)$/.exec(e), n = t[1] || "", r = !!(n && n.charAt(1) !== ":");
		return !!(t[2] || r);
	}
	t.exports = process.platform === "win32" ? r : n, t.exports.posix = n, t.exports.win32 = r;
})), r = /* @__PURE__ */ t(((t, n) => {
	var r = e("util"), i = e("path"), a = e("child_process").spawn, o = "HKLM", s = "HKCU", c = "HKCR", l = "HKU", u = "HKCC", d = [
		o,
		s,
		c,
		l,
		u
	], f = "REG_SZ", p = "REG_MULTI_SZ", m = "REG_EXPAND_SZ", h = "REG_DWORD", g = "REG_QWORD", _ = "REG_BINARY", v = "REG_NONE", y = [
		f,
		p,
		m,
		h,
		g,
		_,
		v
	], b = "", x = /(\\[a-zA-Z0-9_\s]+)*/, S = /^(HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER|HKEY_CLASSES_ROOT|HKEY_USERS|HKEY_CURRENT_CONFIG)(.*)$/, C = /^(.*)\s(REG_SZ|REG_MULTI_SZ|REG_EXPAND_SZ|REG_DWORD|REG_QWORD|REG_BINARY|REG_NONE)\s+([^\s].*)$/;
	function w(e, t) {
		if (!(this instanceof w)) return new w(e, t);
		Error.captureStackTrace(this, w), this.__defineGetter__("name", function() {
			return w.name;
		}), this.__defineGetter__("message", function() {
			return e;
		}), this.__defineGetter__("code", function() {
			return t;
		});
	}
	r.inherits(w, Error);
	function T(e) {
		var t = {
			stdout: "",
			stderr: ""
		};
		return e.stdout.on("data", function(e) {
			t.stdout += e.toString();
		}), e.stderr.on("data", function(e) {
			t.stderr += e.toString();
		}), t;
	}
	function E(e, t, n) {
		var i = n.stdout.trim(), a = n.stderr.trim();
		return new w(r.format("%s command exited with code %d:\n%s\n%s", e, t, i, a), t);
	}
	function D(e) {
		if (e == "x64") return "64";
		if (e == "x86") return "32";
		throw Error("illegal architecture: " + e + " (use x86 or x64)");
	}
	function O(e, t) {
		t && e.push("/reg:" + D(t));
	}
	function k() {
		return process.platform === "win32" ? i.join(process.env.windir, "system32", "reg.exe") : "REG";
	}
	function A(e, t, n, r, i, a, o) {
		if (!(this instanceof A)) return new A(e, t, n, r, i, a, o);
		var s = e, c = t, l = n, u = r, d = i, f = a, p = o;
		this.__defineGetter__("host", function() {
			return s;
		}), this.__defineGetter__("hive", function() {
			return c;
		}), this.__defineGetter__("key", function() {
			return l;
		}), this.__defineGetter__("name", function() {
			return u;
		}), this.__defineGetter__("type", function() {
			return d;
		}), this.__defineGetter__("value", function() {
			return f;
		}), this.__defineGetter__("arch", function() {
			return p;
		});
	}
	r.inherits(A, Object);
	function j(e) {
		if (!(this instanceof j)) return new j(e);
		var t = e || {}, n = "" + (t.host || ""), r = "" + (t.hive || o), i = "" + (t.key || ""), a = t.arch || null;
		if (this.__defineGetter__("host", function() {
			return n;
		}), this.__defineGetter__("hive", function() {
			return r;
		}), this.__defineGetter__("key", function() {
			return i;
		}), this.__defineGetter__("path", function() {
			return (n.length == 0 ? "" : "\\\\" + n + "\\") + r + i;
		}), this.__defineGetter__("arch", function() {
			return a;
		}), this.__defineGetter__("parent", function() {
			var e = i.lastIndexOf("\\");
			return new j({
				host: this.host,
				hive: this.hive,
				key: e == -1 ? "" : i.substring(0, e),
				arch: this.arch
			});
		}), d.indexOf(r) == -1) throw Error("illegal hive specified.");
		if (!x.test(i)) throw Error("illegal key specified.");
		if (a && a != "x64" && a != "x86") throw Error("illegal architecture specified (use x86 or x64)");
	}
	j.HKLM = o, j.HKCU = s, j.HKCR = c, j.HKU = l, j.HKCC = u, j.HIVES = d, j.REG_SZ = f, j.REG_MULTI_SZ = p, j.REG_EXPAND_SZ = m, j.REG_DWORD = h, j.REG_QWORD = g, j.REG_BINARY = _, j.REG_NONE = v, j.REG_TYPES = y, j.DEFAULT_VALUE = b, j.prototype.values = function(e) {
		if (typeof e != "function") throw TypeError("must specify a callback");
		var t = ["QUERY", this.path];
		O(t, this.arch);
		var n = a(k(), t, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), r = "", i = this, o = null, s = T(n);
		return n.on("close", function(t) {
			if (!o) if (t !== 0) "" + t, e(E("QUERY", t, s), null);
			else {
				for (var n = [], a = [], c = r.split("\n"), l = 0, u = 0, d = c.length; u < d; u++) {
					var f = c[u].trim();
					f.length > 0 && (l != 0 && n.push(f), ++l);
				}
				for (var u = 0, d = n.length; u < d; u++) {
					var p = C.exec(n[u]), m, h, g;
					p && (m = p[1].trim(), h = p[2].trim(), g = p[3], a.push(new A(i.host, i.hive, i.key, m, h, g, i.arch)));
				}
				e(null, a);
			}
		}), n.stdout.on("data", function(e) {
			r += e.toString();
		}), n.on("error", function(t) {
			o = t, e(t);
		}), this;
	}, j.prototype.keys = function(e) {
		if (typeof e != "function") throw TypeError("must specify a callback");
		var t = ["QUERY", this.path];
		O(t, this.arch);
		var n = a(k(), t, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), r = "", i = this, o = null, s = T(n);
		return n.on("close", function(t) {
			o || t !== 0 && ("" + t, e(E("QUERY", t, s), null));
		}), n.stdout.on("data", function(e) {
			r += e.toString();
		}), n.stdout.on("end", function() {
			for (var t = [], n = [], a = r.split("\n"), o = 0, s = a.length; o < s; o++) {
				var c = a[o].trim();
				c.length > 0 && t.push(c);
			}
			for (var o = 0, s = t.length; o < s; o++) {
				var l = S.exec(t[o]), u;
				l && (l[1], u = l[2], u && u !== i.key && n.push(new j({
					host: i.host,
					hive: i.hive,
					key: u,
					arch: i.arch
				})));
			}
			e(null, n);
		}), n.on("error", function(t) {
			o = t, e(t);
		}), this;
	}, j.prototype.get = function(e, t) {
		if (typeof t != "function") throw TypeError("must specify a callback");
		var n = ["QUERY", this.path];
		e == "" ? n.push("/ve") : n = n.concat(["/v", e]), O(n, this.arch);
		var r = a(k(), n, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), i = "", o = this, s = null, c = T(r);
		return r.on("close", function(e) {
			if (!s) if (e !== 0) "" + e, t(E("QUERY", e, c), null);
			else {
				for (var n = [], r = null, a = i.split("\n"), l = 0, u = 0, d = a.length; u < d; u++) {
					var f = a[u].trim();
					f.length > 0 && (l != 0 && n.push(f), ++l);
				}
				var p = n[n.length - 1] || "", m = C.exec(p), h, g, _;
				m && (h = m[1].trim(), g = m[2].trim(), _ = m[3], r = new A(o.host, o.hive, o.key, h, g, _, o.arch)), t(null, r);
			}
		}), r.stdout.on("data", function(e) {
			i += e.toString();
		}), r.on("error", function(e) {
			s = e, t(e);
		}), this;
	}, j.prototype.set = function(e, t, n, r) {
		if (typeof r != "function") throw TypeError("must specify a callback");
		if (y.indexOf(t) == -1) throw Error("illegal type specified.");
		var i = ["ADD", this.path];
		e == "" ? i.push("/ve") : i = i.concat(["/v", e]), i = i.concat([
			"/t",
			t,
			"/d",
			n,
			"/f"
		]), O(i, this.arch);
		var o = a(k(), i, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), s = null, c = T(o);
		return o.on("close", function(e) {
			s || (e === 0 ? r(null) : ("" + e, r(E("ADD", e, c, null))));
		}), o.stdout.on("data", function(e) {
			"" + e;
		}), o.on("error", function(e) {
			s = e, r(e);
		}), this;
	}, j.prototype.remove = function(e, t) {
		if (typeof t != "function") throw TypeError("must specify a callback");
		var n = e ? [
			"DELETE",
			this.path,
			"/f",
			"/v",
			e
		] : [
			"DELETE",
			this.path,
			"/f",
			"/ve"
		];
		O(n, this.arch);
		var r = a(k(), n, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), i = null, o = T(r);
		return r.on("close", function(e) {
			i || (e === 0 ? t(null) : ("" + e, t(E("DELETE", e, o), null)));
		}), r.stdout.on("data", function(e) {
			"" + e;
		}), r.on("error", function(e) {
			i = e, t(e);
		}), this;
	}, j.prototype.clear = function(e) {
		if (typeof e != "function") throw TypeError("must specify a callback");
		var t = [
			"DELETE",
			this.path,
			"/f",
			"/va"
		];
		O(t, this.arch);
		var n = a(k(), t, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), r = null, i = T(n);
		return n.on("close", function(t) {
			r || (t === 0 ? e(null) : ("" + t, e(E("DELETE", t, i), null)));
		}), n.stdout.on("data", function(e) {
			"" + e;
		}), n.on("error", function(t) {
			r = t, e(t);
		}), this;
	}, j.prototype.erase = j.prototype.clear, j.prototype.destroy = function(e) {
		if (typeof e != "function") throw TypeError("must specify a callback");
		var t = [
			"DELETE",
			this.path,
			"/f"
		];
		O(t, this.arch);
		var n = a(k(), t, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), r = null, i = T(n);
		return n.on("close", function(t) {
			r || (t === 0 ? e(null) : ("" + t, e(E("DELETE", t, i), null)));
		}), n.stdout.on("data", function(e) {
			"" + e;
		}), n.on("error", function(t) {
			r = t, e(t);
		}), this;
	}, j.prototype.create = function(e) {
		if (typeof e != "function") throw TypeError("must specify a callback");
		var t = [
			"ADD",
			this.path,
			"/f"
		];
		O(t, this.arch);
		var n = a(k(), t, {
			cwd: void 0,
			env: process.env,
			stdio: [
				"ignore",
				"pipe",
				"pipe"
			]
		}), r = null, i = T(n);
		return n.on("close", function(t) {
			r || (t === 0 ? e(null) : ("" + t, e(E("ADD", t, i), null)));
		}), n.stdout.on("data", function(e) {
			"" + e;
		}), n.on("error", function(t) {
			r = t, e(t);
		}), this;
	}, j.prototype.keyExists = function(e) {
		return this.values(function(t, n) {
			if (t) return t.code == 1 ? e(null, !1) : e(t);
			e(null, !0);
		}), this;
	}, j.prototype.valueExists = function(e, t) {
		return this.get(e, function(e, n) {
			if (e) return e.code == 1 ? t(null, !1) : t(e);
			t(null, !0);
		}), this;
	}, n.exports = j;
})), i = /* @__PURE__ */ t(((t, n) => {
	var i, a = e("fs"), o = e("path"), s;
	i = r(), s = new i({
		hive: i.HKCU,
		key: "\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
	}), n.exports = {
		enable: function(e) {
			var t = e.appName, n = e.appPath, r = e.isHiddenOnLaunch;
			return new Promise(function(e, c) {
				var l, u = n, d;
				return l = "", d = o.join(o.dirname(process.execPath), "..", "update.exe"), process.versions?.electron != null && a.existsSync(d) ? (u = d, l = " --processStart \"" + o.basename(process.execPath) + "\"", r && (l += " --process-start-args \"--hidden\"")) : r && (l += " --hidden"), s.set(t, i.REG_SZ, "\"" + u + "\"" + l, function(t) {
					return t == null ? e() : c(t);
				});
			});
		},
		disable: function(e) {
			return new Promise(function(t, n) {
				return s.remove(e, function(e) {
					return e == null ? t() : e.message.indexOf("The system was unable to find the specified registry key or value") === -1 ? n(e) : t(!1);
				});
			});
		},
		isEnabled: function(e) {
			return new Promise(function(t, n) {
				return s.get(e, function(e, n) {
					return t(e == null ? n != null : !1);
				});
			});
		}
	};
})), a = /* @__PURE__ */ t(((e) => {
	e.parse = function(e) {
		if (e.length != 0) return t.call({
			value: e,
			index: 0
		});
	};
	function t() {
		var t = this.value[this.index];
		switch (t) {
			case "{": return e.ArrayParser.call(this);
			case "\"": return e.StringParser.call(this);
			case "a":
				if (this.value.substring(this.index, this.index + 5) == "alias") return e.AliasParser.call(this);
				break;
			case "«":
				if (this.value.substring(this.index, this.index + 5) == "«data") return e.DataParser.call(this);
				break;
		}
		return isNaN(t) ? e.UndefinedParser.call(this) : e.NumberParser.call(this);
	}
	e.AliasParser = function() {
		return this.index += 6, "/Volumes/" + e.StringParser.call(this).replace(/:/g, "/");
	}, e.ArrayParser = function() {
		for (var e = [], n = this.value[++this.index]; n != "}";) e.push(t.call(this)), this.value[this.index] == "," && (this.index += 2), n = this.value[this.index];
		return this.index++, e;
	}, e.DataParser = function() {
		var t = e.UndefinedParser.call(this);
		t = t.substring(6, t.length - 1);
		var n = t.substring(0, 4);
		t = t.substring(4, t.length);
		for (var r = new Buffer(t.length / 2), i = 0, a = 0, o = t.length; a < o; a += 2) r[i++] = parseInt(t[a] + t[a + 1], 16);
		return r.type = n, r;
	}, e.NumberParser = function() {
		return Number(e.UndefinedParser.call(this));
	}, e.StringParser = function(e) {
		for (var t = "", n = ++this.index, r = this.value[n++]; r != "\"";) r == "\\" && (t += this.value.substring(this.index, n - 1), this.index = n++), r = this.value[n++];
		return t += this.value.substring(this.index, n - 1), this.index = n, t;
	};
	var n = /}|,|\n/;
	e.UndefinedParser = function() {
		for (var e = this.index, t = this.value[e++]; !n.test(t);) t = this.value[e++];
		var r = this.value.substring(this.index, e - 1);
		return this.index = e - 1, r;
	};
})), o = /* @__PURE__ */ t(((t) => {
	var n = e("child_process").spawn;
	t.Parsers = a();
	var r = t.Parsers.parse;
	t.osascript = "osascript", t.execFile = function(e, t, n) {
		return Array.isArray(t) || (n = t, t = []), i(e, t, n);
	}, t.execString = function(e, t) {
		return i(e, t);
	};
	function i(e, i, a) {
		var s = !1;
		Array.isArray(i) || (a = i, i = [], s = !0), i.push("-ss"), s || i.push(e);
		var c = n(t.osascript, i);
		o(c.stdout), o(c.stderr), c.on("exit", function(t) {
			var n = r(c.stdout.body), i;
			t && (i = Error(c.stderr.body), i.appleScript = e, i.exitCode = t), a && a(i, n, c.stderr.body);
		}), s && (c.stdin.write(e), c.stdin.end());
	}
	function o(e) {
		e.body = "", e.setEncoding("utf8"), e.on("data", function(t) {
			e.body += t;
		});
	}
})), s = /* @__PURE__ */ t(((t, n) => {
	var r = e("os").homedir();
	n.exports = (e) => {
		if (typeof e != "string") throw TypeError(`Expected a string, got ${typeof e}`);
		return r ? e.replace(/^~(?=$|\/|\\)/, r) : e;
	};
})), c = /* @__PURE__ */ t(((t, n) => {
	var r = e("path"), i = e("fs"), a = 511;
	n.exports = o.mkdirp = o.mkdirP = o;
	function o(e, t, n, s) {
		typeof t == "function" ? (n = t, t = {}) : (!t || typeof t != "object") && (t = { mode: t });
		var c = t.mode, l = t.fs || i;
		c === void 0 && (c = a), s ||= null;
		var u = n || function() {};
		e = r.resolve(e), l.mkdir(e, c, function(n) {
			if (!n) return s ||= e, u(null, s);
			switch (n.code) {
				case "ENOENT":
					/* istanbul ignore if */
					if (r.dirname(e) === e) return u(n);
					o(r.dirname(e), t, function(n, r) {
						/* istanbul ignore if */
						n ? u(n, r) : o(e, t, u, r);
					});
					break;
				default:
					l.stat(e, function(e, t) {
						e || !t.isDirectory() ? u(n, s) : u(null, s);
					});
					break;
			}
		});
	}
	o.sync = function e(t, n, o) {
		(!n || typeof n != "object") && (n = { mode: n });
		var s = n.mode, c = n.fs || i;
		s === void 0 && (s = a), o ||= null, t = r.resolve(t);
		try {
			c.mkdirSync(t, s), o ||= t;
		} catch (i) {
			switch (i.code) {
				case "ENOENT":
					o = e(r.dirname(t), n, o), e(t, n, o);
					break;
				default:
					var l;
					try {
						l = c.statSync(t);
					} catch 					/* istanbul ignore next */ {
						throw i;
					}
					/* istanbul ignore if */
					if (!l.isDirectory()) throw i;
					break;
			}
		}
		return o;
	};
})), l = /* @__PURE__ */ t(((t, n) => {
	var r = e("fs"), i = c();
	n.exports = {
		createFile: function(e) {
			var t, n = e.directory, a = e.filePath;
			return t = e.data, new Promise(function(e, o) {
				return i(n, function(n) {
					return n == null ? r.writeFile(a, t, function(t) {
						return t == null ? e() : o(t);
					}) : o(n);
				});
			});
		},
		isEnabled: function(e) {
			return new Promise((function(t) {
				return function(t, n) {
					return r.stat(e, function(e, n) {
						return t(e == null ? n != null : !1);
					});
				};
			})(this));
		},
		removeFile: function(e) {
			return new Promise((function(t) {
				return function(t, n) {
					return r.stat(e, function(i) {
						return i == null ? r.unlink(e, function(e) {
							return e == null ? t() : n(e);
						}) : t();
					});
				};
			})(this));
		}
	};
})), u = /* @__PURE__ */ t(((e, t) => {
	var n, r, i, a = [].indexOf || function(e) {
		for (var t = 0, n = this.length; t < n; t++) if (t in this && this[t] === e) return t;
		return -1;
	};
	n = o(), i = s(), r = l(), t.exports = {
		enable: function(e) {
			var t = e.appName, n = e.appPath, i, a = e.isHiddenOnLaunch, o, s = e.mac, c, l, u;
			return s.useLaunchAgent ? (c = [n], a && c.push("--hidden"), l = c.map(function(e) {
				return "    <string>" + e + "</string>";
			}).join("\n"), i = "<?xml version=\"1.0\" encoding=\"UTF-8\"?>\n<!DOCTYPE plist PUBLIC \"-//Apple//DTD PLIST 1.0//EN\" \"http://www.apple.com/DTDs/PropertyList-1.0.dtd\">\n<plist version=\"1.0\">\n<dict>\n  <key>Label</key>\n  <string>" + t + "</string>\n  <key>ProgramArguments</key>\n  <array>\n  " + l + "\n  </array>\n  <key>RunAtLoad</key>\n  <true/>\n</dict>\n</plist>", r.createFile({
				data: i,
				directory: this.getDirectory(),
				filePath: this.getFilePath(t)
			})) : (o = a ? "true" : "false", u = "{path:\"" + n + "\", hidden:" + o + ", name:\"" + t + "\"}", this.execApplescriptCommand("make login item at end with properties " + u));
		},
		disable: function(e, t) {
			return t.useLaunchAgent ? r.removeFile(this.getFilePath(e)) : this.execApplescriptCommand("delete login item \"" + e + "\"");
		},
		isEnabled: function(e, t) {
			return t.useLaunchAgent ? r.isEnabled(this.getFilePath(e)) : this.execApplescriptCommand("get the name of every login item").then(function(t) {
				return t != null && a.call(t, e) >= 0;
			});
		},
		execApplescriptCommand: function(e) {
			return new Promise(function(t, r) {
				return n.execString("tell application \"System Events\" to " + e, function(e, n) {
					return e == null ? t(n) : r(e);
				});
			});
		},
		getDirectory: function() {
			return i("~/Library/LaunchAgents/");
		},
		getFilePath: function(e) {
			return "" + this.getDirectory() + e + ".plist";
		}
	};
})), d = /* @__PURE__ */ t(((e, t) => {
	var n, r = s();
	n = l(), t.exports = {
		enable: function(e) {
			var t = e.appName, r = e.appPath, i, a = e.isHiddenOnLaunch ? " --hidden" : "";
			return i = "[Desktop Entry]\nType=Application\nVersion=1.0\nName=" + t + "\nComment=" + t + "startup script\nExec=" + r + a + "\nStartupNotify=false\nTerminal=false", n.createFile({
				data: i,
				directory: this.getDirectory(),
				filePath: this.getFilePath(t)
			});
		},
		disable: function(e) {
			return n.removeFile(this.getFilePath(e));
		},
		isEnabled: function(e) {
			return n.isEnabled(this.getFilePath(e));
		},
		getDirectory: function() {
			return r("~/.config/autostart/");
		},
		getFilePath: function(e) {
			return "" + this.getDirectory() + e + ".desktop";
		}
	};
})), f = /* @__PURE__ */ t(((e, t) => {
	var r, a = function(e, t) {
		return function() {
			return e.apply(t, arguments);
		};
	};
	r = n(), t.exports = (function() {
		function e(e) {
			var t, n, o = e.name, s, c;
			if (t = e.isHidden, n = e.mac, s = e.path, this.fixOpts = a(this.fixOpts, this), this.isEnabled = a(this.isEnabled, this), this.disable = a(this.disable, this), this.enable = a(this.enable, this), o == null) throw Error("You must specify a name");
			if (this.opts = {
				appName: o,
				isHiddenOnLaunch: t ?? !1,
				mac: n ?? {}
			}, c = typeof process < "u" && process !== null ? process.versions : void 0, s != null) {
				if (!r(s)) throw Error("path must be absolute");
				this.opts.appPath = s;
			} else if (c != null && (c.nw != null || c["node-webkit"] != null || c.electron != null)) this.opts.appPath = process.execPath;
			else throw Error("You must give a path (this is only auto-detected for NW.js and Electron apps)");
			if (this.fixOpts(), this.api = null, /^win/.test(process.platform)) this.api = i();
			else if (/darwin/.test(process.platform)) this.api = u();
			else if (/linux/.test(process.platform) || /freebsd/.test(process.platform)) this.api = d();
			else throw Error("Unsupported platform");
		}
		return e.prototype.enable = function() {
			return this.api.enable(this.opts);
		}, e.prototype.disable = function() {
			return this.api.disable(this.opts.appName, this.opts.mac);
		}, e.prototype.isEnabled = function() {
			return this.api.isEnabled(this.opts.appName, this.opts.mac);
		}, e.prototype.fixMacExecPath = function(e, t) {
			return e = e.replace(/(^.+?[^\/]+?\.app)\/Contents\/(Frameworks\/((\1|[^\/]+?) Helper)\.app\/Contents\/MacOS\/\3|MacOS\/Electron)/, "$1"), t.useLaunchAgent || (e = e.replace(/\.app\/Contents\/MacOS\/[^\/]*$/, ".app")), e;
		}, e.prototype.fixOpts = function() {
			var e;
			if (this.opts.appPath = this.opts.appPath.replace(/\/$/, ""), /darwin/.test(process.platform) && (this.opts.appPath = this.fixMacExecPath(this.opts.appPath, this.opts.mac)), this.opts.appPath.indexOf("/") === -1 ? this.opts.appPath.indexOf("\\") !== -1 && (e = this.opts.appPath.split("\\"), this.opts.appName = e[e.length - 1], this.opts.appName = this.opts.appName.substr(0, this.opts.appName.length - 4)) : (e = this.opts.appPath.split("/"), this.opts.appName = e[e.length - 1]), /darwin/.test(process.platform) && this.opts.appName.indexOf(".app", this.opts.appName.length - 4) !== -1) return this.opts.appName = this.opts.appName.substr(0, this.opts.appName.length - 4);
		}, e;
	})();
}));
//#endregion
export default f();
export {};
