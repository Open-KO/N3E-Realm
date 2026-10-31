#pragma once
// Compiled only into tools builds. Drafts contain typed package values, no
// assets, shell commands, credentials, collision, or gameplay-state reflection.
#include "network/world.h"
#include "render/orbit.h"
#include <fstream>
#include <imgui.h>
#include <random>
#include <sstream>
namespace n3e {
class Editor {
  std::vector<float> draft;
  std::vector<std::vector<float>> undo, redo;
  std::vector<std::string> history, completion, output;
  int history_at = 0, selected = 0, spawn_index = 0;
  // PQ-186/PQ-189/PQ-194: the NPC a `trace`, `record` or `kill` request names
  uint64_t trace_entity = 0;
  char command[256]{}, reason[161] = "editor publication",
                       filename[65] = "draft", request[65]{};
  bool initialized = false, dirty = false, terminal_focus = false,
       follow = true;
  float terminal_height = 0;
  uint64_t base_revision = 0, revert_revision = 0;
  std::string message, shown_result;
  AdminRequest last_request;
  // Bounded scrollback. Transcript lines are local text, never remote content
  // beyond the typed results the server already returned to this character.
  void echo(std::string line) {
    if (output.size() == 512)
      output.erase(output.begin());
    output.push_back(std::move(line));
    follow = true;
  }
  void say(std::string line) {
    message = line;
    echo(std::move(line));
  }
  static std::string number(float v) {
    char buffer[32];
    std::snprintf(buffer, sizeof buffer, "%.3f", v);
    std::string s(buffer);
    while (s.size() > 1 && s.back() == '0')
      s.pop_back();
    if (!s.empty() && s.back() == '.')
      s.pop_back();
    return s;
  }
  // "demo:decoration.banner.x" -> object "decoration.banner", field "x".
  static std::pair<std::string, std::string> split(const std::string &key) {
    auto start = key.find(':');
    std::string bare = start == std::string::npos ? key : key.substr(start + 1);
    auto dot = bare.rfind('.');
    if (dot == std::string::npos)
      return {bare, bare};
    return {bare.substr(0, dot), bare.substr(dot + 1)};
  }
  void checkpoint() {
    if (undo.size() == 64)
      undo.erase(undo.begin());
    undo.push_back(draft);
    redo.clear();
    dirty = true;
  }
  std::string fresh() {
    std::random_device rng;
    std::ostringstream o;
    o << std::hex << rng() << rng() << rng() << rng();
    return o.str();
  }
  void send(WorldClient *client, const WorldState &w, const Release &r,
            std::string op, std::string id = "") {
    if (!client || !w.world.session()) {
      say("Connect and select a character first");
      return;
    }
    Envelope e;
    auto *q = e.mutable_admin_request();
    q->set_session(w.world.session());
    q->set_id(id.empty() ? fresh() : id);
    q->set_operation(op);
    q->set_expected(base_revision);
    q->set_base(r.hash);
    q->set_reason(reason);
    q->set_revision(revert_revision);
    q->set_spawn(spawn_index < 0 ? 0 : spawn_index);
    if (op == "trace" || op == "record" || op == "kill")
      q->set_entity(trace_entity);
    if (op == "publish")
      for (size_t i = 0; i < draft.size(); ++i) {
        auto *v = q->add_patch();
        v->set_key(r.editing[i].key);
        v->set_value(draft[i]);
      }
    last_request = *q;
    client->send(e);
    say("Pending " + q->id());
  }
  void disk(const Release &r, bool save) {
    std::string name = filename;
    if (name.empty() || name.size() > 64 ||
        name.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTU"
                               "VWXYZ0123456789_-") != std::string::npos) {
      say("Use a simple draft name");
      return;
    }
    std::filesystem::create_directories("build/drafts");
    auto path = std::filesystem::path("build/drafts") / (name + ".n3draft");
    if (std::filesystem::is_symlink(path)) {
      say("Symlink refused");
      return;
    }
    if (save) {
      Revision s;
      s.set_base(r.hash);
      s.set_revision(base_revision);
      for (size_t i = 0; i < draft.size(); ++i) {
        auto *v = s.add_values();
        v->set_key(r.editing[i].key);
        v->set_value(draft[i]);
      }
      std::ofstream f(path, std::ios::binary);
      bool saved = s.SerializeToOstream(&f);
      say(saved ? "Saved " + path.string() : "Save failed");
    } else {
      if (!std::filesystem::exists(path) ||
          std::filesystem::file_size(path) > 32768) {
        say("Missing or oversized draft");
        return;
      }
      Revision s;
      std::ifstream f(path, std::ios::binary);
      if (!s.ParseFromIstream(&f) || s.base() != r.hash ||
          s.values_size() != int(draft.size())) {
        say("Incompatible draft base/schema");
        return;
      }
      for (size_t i = 0; i < draft.size(); ++i) {
        const auto &v = s.values(i);
        const auto &p = r.editing[i];
        if (v.key() != p.key || !std::isfinite(v.value()) ||
            v.value() < p.min || v.value() > p.max) {
          say("Invalid draft property");
          return;
        }
      }
      checkpoint();
      for (size_t i = 0; i < draft.size(); ++i)
        draft[i] = s.values(i).value();
      base_revision = s.revision();
      say("Loaded local draft");
    }
  }
  // Read-only inspection of the package's own typed registry and local draft.
  float live_value(const Release &r, const WorldState &w, size_t i) const {
    if (w.world.revision().base() == r.hash &&
        w.world.revision().values_size() == int(draft.size()))
      return w.world.revision().values(i).value();
    return r.editing[i].initial;
  }
  void list(const Release &r, const WorldState &w, const std::string &filter) {
    size_t shown = 0;
    for (size_t i = 0; i < r.editing.size(); ++i) {
      const auto &p = r.editing[i];
      if (!filter.empty() && p.key.find(filter) == std::string::npos)
        continue;
      ++shown;
      if (p.kind == 6) {
        echo("  " + p.key + " = scene.bin (only prepackaged prefab)");
        continue;
      }
      std::string line = "  " + p.key + " = " + number(draft[i]);
      float current = live_value(r, w, i);
      if (std::abs(current - draft[i]) > 1e-6f)
        line += " (draft; live " + number(current) + ")";
      echo(line + "  [" + number(p.min) + " .. " + number(p.max) + "]");
    }
    echo(std::to_string(shown) + " of " + std::to_string(r.editing.size()) +
         " editable properties" +
         (filter.empty() ? "" : " matching \"" + filter + "\""));
  }
  void scene(const Release &r, const WorldState &w) {
    echo("release " + r.hash.substr(0, 12) + " | game " + r.game +
         " | live revision " +
         std::to_string(w.world.revision().revision()) + " | draft base " +
         std::to_string(base_revision) + " | " +
         (dirty ? "LOCAL DRAFT" : "matching live"));
    std::string object, line;
    for (size_t i = 0; i < r.editing.size(); ++i) {
      auto [owner, field] = split(r.editing[i].key);
      if (owner != object) {
        if (!line.empty())
          echo(line);
        object = owner;
        line = "  " + owner + ":";
      }
      line += " " + field + "=" +
              (r.editing[i].kind == 6 ? "scene.bin" : number(draft[i]));
    }
    if (!line.empty())
      echo(line);
    echo("Editable objects only. Collision, events, terrain, players and live "
         "NPCs are not editable properties.");
  }
  void describe(const Release &r, const WorldState &w,
                const std::string &key) {
    for (size_t i = 0; i < r.editing.size(); ++i) {
      const auto &p = r.editing[i];
      if (p.key != key)
        continue;
      echo("  " + p.key + " = " +
           (p.kind == 6 ? "scene.bin" : number(draft[i])) + " | live " +
           (p.kind == 6 ? "scene.bin" : number(live_value(r, w, i))) +
           " | range " + number(p.min) + " .. " + number(p.max));
      if (w.registry.properties_size() == int(r.editing.size()) &&
          w.registry.properties(i).key() == p.key) {
        const auto &m = w.registry.properties(i);
        echo("  " + m.type() + " | " + m.scope() + " | " + m.capability() +
             " | " + m.persistence() + " | " + m.activation() + " | schema " +
             std::to_string(m.schema()));
      } else
        echo("  server registry not loaded; run registry");
      message = "get " + key;
      return;
    }
    say("Unknown property; use list");
  }
  void execute(const Release &r, const WorldState &w, WorldClient *c) {
    std::string line = command;
    if (line.empty())
      return;
    command[0] = 0;
    echo("> " + line);
    std::istringstream in(line);
    std::string op, key;
    in >> op;
    // Store only the recognized command name, never arbitrary input or secrets.
    const std::vector<std::string> verbs = {
        "help",   "set",    "publish", "revert",   "status", "retry",
        "inspect", "spawn", "registry", "list",    "scene",  "get",
        "draft",  "clear", "trace", "record", "show", "hide", "kill"};
    if (std::find(verbs.begin(), verbs.end(), op) != verbs.end()) {
      if (history.size() == 64)
        history.erase(history.begin());
      history.push_back(op);
      history_at = history.size();
    }
    if (op == "help")
      say("help | list [TEXT] | scene | get KEY | draft | clear | set KEY "
          "NUMBER | publish | revert REV | status ID | retry | inspect | "
          "spawn INDEX | trace NPC_ID | record NPC_ID | show | hide | "
          "kill [NPC_ID] | registry. "
          "Weather/time and gameplay-state setters "
          "excluded.");
    else if (op == "list") {
      in >> key;
      list(r, w, in ? key : std::string());
      message = "list";
    } else if (op == "scene") {
      scene(r, w);
      message = "scene";
    } else if (op == "get") {
      if (in >> key)
        describe(r, w, key);
      else
        say("Usage: get KEY");
    } else if (op == "draft") {
      size_t changed = 0;
      for (size_t i = 0; i < draft.size(); ++i)
        if (std::abs(draft[i] - live_value(r, w, i)) > 1e-6f)
          ++changed;
      say((dirty ? "LOCAL DRAFT" : "matching live") + std::string(" | ") +
          std::to_string(changed) + " changed of " +
          std::to_string(draft.size()) + " | base " +
          std::to_string(base_revision) + " | live " +
          std::to_string(w.world.revision().revision()) + " | " +
          std::to_string(undo.size()) + " undo / " +
          std::to_string(redo.size()) + " redo");
    } else if (op == "clear") {
      output.clear();
      message = "clear";
    } else if (op == "set") {
      float value;
      in >> key >> value;
      auto it = std::find_if(r.editing.begin(), r.editing.end(),
                             [&](auto &p) { return p.key == key; });
      if (in && it != r.editing.end() && std::isfinite(value) &&
          value >= it->min && value <= it->max) {
        checkpoint();
        draft[it - r.editing.begin()] = value;
        say("Local draft changed: " + key + " = " + number(value));
      } else
        say("Invalid typed key/value");
    } else if (op == "status") {
      in >> key;
      send(c, w, r, op, key);
    } else if (op == "retry") {
      if (c && !last_request.id().empty()) {
        Envelope e;
        *e.mutable_admin_request() = last_request;
        e.mutable_admin_request()->set_session(w.world.session());
        c->send(e);
        say("Retrying " + last_request.id());
      } else
        say("Nothing to retry");
    } else if (op == "revert") {
      if (in >> revert_revision)
        send(c, w, r, op);
      else
        say("Usage: revert REVISION");
    } else if (op == "spawn") {
      if (in >> spawn_index)
        send(c, w, r, op);
      else
        say("Usage: spawn INDEX");
    } else if (op == "trace") {
      // PQ-186 (KO: the operator command +actpursue, Ebenezer 0042c1ba): the
      // server authorizes the mark against this character's roles and then
      // reports the NPC's AI state to sessions holding server.inspect.
      if (in >> trace_entity && trace_entity)
        send(c, w, r, op);
      else
        say("Usage: trace NPC_ID");
    } else if (op == "record") {
      // PQ-189 (KO: the operator command +pursue, Ebenezer 0042c1ba): the
      // server writes the NPC's state to its own log; the result is a status.
      if (in >> trace_entity && trace_entity)
        send(c, w, r, op);
      else
        say("Usage: record NPC_ID");
    } else if (op == "kill") {
      // PQ-194 (D-157): the server checks entity.kill against this character,
      // audits the request with the Reason field and kills the NPC through
      // its ordinary death path; the result is killed or a refusal. With no
      // id it names the viewer's current target (any server check applies).
      std::string id;
      if (in >> id) {
        std::istringstream number(id);
        if (number >> trace_entity && number.eof() && trace_entity)
          send(c, w, r, op);
        else
          say("Usage: kill [NPC_ID]");
      } else if (selection) {
        trace_entity = selection;
        send(c, w, r, op);
      } else
        say("Select an NPC first, or use kill NPC_ID");
    } else if (op == "show" || op == "hide") {
      // PQ-192 (KO: the operator commands VIEW and UNVIEW, client 0054e180):
      // the server shows this server.inspect holder to ordinary players for
      // the session, or withholds it again; the result is shown or hidden.
      send(c, w, r, op);
    } else if (op == "publish" || op == "inspect" || op == "registry")
      send(c, w, r, op);
    else
      say("Unsupported command; use help");
  }

public:
  bool open = false, terminal_open = false, preview = true;
  // PQ-194: the viewer's current target, which `kill` with no id sends.
  uint64_t selection = 0;
  void toggle_terminal() {
    terminal_open = !terminal_open;
    terminal_focus = terminal_open;
  }
#if N3E_HARNESS
  // Editor replay (N3E_EDIT_TEST, test client only): draft save/load, publish.
  void smoke(const Release &r, const WorldState &w, WorldClient *c) {
    live(r, w);
    open = true;
    checkpoint();
    draft[0] = .25f;
    snprintf(filename, sizeof filename, "p4-smoke");
    disk(r, true);
    draft[0] = .9f;
    disk(r, false);
    if (draft[0] != .25f)
      throw std::runtime_error("draft save/load failed");
    send(c, w, r, "publish");
  }
#endif
  bool capture() const { return open || terminal_open; }
  bool help_visible() const { return message.starts_with("help | list"); }
  const std::vector<std::string> &lines() const { return output; }
  bool logged(const std::string &text) const {
    for (const auto &line : output)
      if (line.find(text) != std::string::npos)
        return true;
    return false;
  }
  const std::vector<float> &values() const { return draft; }
  void init(const Release &r) {
    if (!initialized) {
      for (auto &p : r.editing)
        draft.push_back(p.initial);
      initialized = true;
    }
  }
  void live(const Release &r, const WorldState &w) {
    init(r);
    if (!dirty && w.world.has_revision() &&
        w.world.revision().base() == r.hash &&
        w.world.revision().values_size() == int(draft.size())) {
      for (size_t i = 0; i < draft.size(); ++i)
        draft[i] = w.world.revision().values(i).value();
      base_revision = w.world.revision().revision();
    }
  }
  void draw(const Release &r, const WorldState &w, WorldClient *c,
            const Orbit &orbit, int width, int height) {
    live(r, w);
    // Asynchronous typed results join the transcript once, in order.
    if (!w.admin.id().empty()) {
      std::string current =
          "[" + w.admin.id().substr(0, 8) + "] " + w.admin.status() +
          " (revision " + std::to_string(w.admin.revision()) + ", tick " +
          std::to_string(w.admin.tick()) + ")";
      if (w.admin.status() == "conflict" && w.admin.has_state())
        for (auto &v : w.admin.state().values())
          current += "\n  live " + v.key() + " = " + number(v.value());
      if (current != shown_result) {
        shown_result = current;
        echo(current);
      }
    }
    if (open && !r.editing.empty()) {
      ImGui::SetNextWindowPos(ImVec2(8, 8), ImGuiCond_FirstUseEver);
      ImGui::SetNextWindowSize(
          ImVec2(std::min(510, width - 16), std::min(640, height - 16)),
          ImGuiCond_Always);
      ImGui::Begin("World editor (F11)", &open);
      ImGui::TextWrapped("Press ~ for the terminal; it carries the command "
                         "history and results.");
      ImGui::Text("%s | draft base %llu | live %llu",
                  dirty ? "LOCAL DRAFT" : "LIVE",
                  (unsigned long long)base_revision,
                  (unsigned long long)w.world.revision().revision());
      ImGui::Checkbox("Preview local draft", &preview);
      ImGui::TextUnformatted(
          "Collision and events are frozen. Prefab: scene.bin only.");
      if (ImGui::Button("Reset to live")) {
        dirty = false;
        undo.clear();
        redo.clear();
        live(r, w);
      }
      ImGui::SameLine();
      if (ImGui::Button("Undo") && !undo.empty()) {
        redo.push_back(draft);
        draft = undo.back();
        undo.pop_back();
        dirty = true;
      }
      ImGui::SameLine();
      if (ImGui::Button("Redo") && !redo.empty()) {
        undo.push_back(draft);
        draft = redo.back();
        redo.pop_back();
        dirty = true;
      }
      if (ImGui::TreeNode("Zone hierarchy")) {
        ImGui::Selectable("Lighting", selected == -1);
        if (ImGui::IsItemClicked())
          selected = -1;
        for (auto &p : r.editing)
          if (p.kind == 1) {
            if (ImGui::Selectable(p.key.c_str(), selected == int(p.target)))
              selected = p.target;
          }
        for (const auto &p : r.editing)
          if (p.kind == 7) {
            if (ImGui::Selectable(p.key.c_str(),
                                  selected == 100 + int(p.target)))
              selected = 100 + p.target;
          }
        if (ImGui::Selectable("NPC next-cycle timers", selected == -2))
          selected = -2;
        ImGui::TreePop();
      }
      for (size_t i = 0; i < r.editing.size(); ++i) {
        const auto &p = r.editing[i];
        bool visible = (selected == -1 && p.kind == 0) ||
                       (selected == -2 && p.kind >= 9) ||
                       (selected >= 100 && p.kind >= 7 && p.kind <= 8 &&
                        int(p.target) == selected - 100) ||
                       (selected >= 0 && selected < 8 && p.kind >= 1 &&
                        p.kind <= 6 && int(p.target) == selected);
        if (!visible)
          continue;
        float v = draft[i];
        ImGui::TextWrapped("%s", p.key.c_str());
        ImGui::SetNextItemWidth(-1);
        const auto label = "##" + p.key;
        if (p.kind == 6) {
          int prefab = 0;
          ImGui::Combo(label.c_str(), &prefab, "scene.bin\0\0");
          continue;
        }
        if (ImGui::SliderFloat(label.c_str(), &v, p.min, p.max,
                               p.kind >= 9 ? "%.0f" : "%.3f")) {
          checkpoint();
          draft[i] = p.kind >= 9 ? std::round(v) : v;
        }
        if (ImGui::IsItemHovered()) {
          if (w.registry.properties_size() == int(r.editing.size()) &&
              w.registry.properties(i).key() == p.key) {
            const auto &metadata = w.registry.properties(i);
            ImGui::SetTooltip("%s | %s | %s | %s | %s | schema %u",
                              metadata.type().c_str(), metadata.scope().c_str(),
                              metadata.capability().c_str(),
                              metadata.persistence().c_str(),
                              metadata.activation().c_str(), metadata.schema());
          } else
            ImGui::SetTooltip(
                "number | zone | world.edit | durable | %s | schema 1",
                p.kind >= 7 ? "next spawn cycle" : "next tick");
        }
      }
      ImGui::InputText("Reason", reason, sizeof reason);
      if (ImGui::Button("Publish"))
        send(c, w, r, "publish");
      ImGui::SameLine();
      if (ImGui::Button("Refresh permissions"))
        send(c, w, r, "registry");
      ImGui::InputText("Draft name", filename, sizeof filename);
      if (ImGui::Button("Save draft / export"))
        disk(r, true);
      ImGui::SameLine();
      if (ImGui::Button("Load draft"))
        disk(r, false);
      ImGui::TextWrapped("%s", message.c_str());
      ImGui::End();
    }
    // Separate top-anchored dropdown, independent of the world editor window.
    float panel = std::min(320.f, height * .48f);
    float goal = terminal_open ? panel : 0.f;
    terminal_height += (goal - terminal_height) *
                       std::min(1.f, ImGui::GetIO().DeltaTime * 18.f);
    if (terminal_height > 1.f) {
      ImGui::SetNextWindowPos(ImVec2(0, terminal_height - panel));
      ImGui::SetNextWindowSize(ImVec2(width, panel));
      ImGui::Begin("Terminal (~)", nullptr,
                   ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoResize |
                       ImGuiWindowFlags_NoCollapse |
                       (terminal_open ? 0 : ImGuiWindowFlags_NoInputs));
      ImGui::BeginChild("Output", ImVec2(0, -60), false);
      for (const auto &line : output)
        ImGui::TextWrapped("%s", line.c_str());
      // Follow new output, but leave a reader who scrolled up alone.
      if (follow) {
        ImGui::SetScrollHereY(1.f);
        follow = false;
      }
      ImGui::EndChild();
      ImGui::Separator();
      ImGui::TextUnformatted(
          "Terminal (help; Tab completion; Up/Down history)");
      completion = {"help", "list ", "scene", "get ", "draft",
                    "clear", "set ", "status ", "retry", "registry"};
      for (const auto &cap : w.registry.capabilities()) {
        if (cap == "world.edit") {
          completion.push_back("publish");
          completion.push_back("revert ");
        }
        if (cap == "entity.spawn")
          completion.push_back("spawn ");
        if (cap == "entity.kill")
          completion.push_back("kill");
        if (cap == "server.inspect") {
          completion.push_back("inspect");
          completion.push_back("trace ");
          completion.push_back("record ");
          completion.push_back("show");
          completion.push_back("hide");
        }
      }
      for (const auto &p : w.registry.properties())
        completion.push_back("set " + p.key() + " ");
      for (const auto &p : r.editing)
        completion.push_back("get " + p.key);
      auto callback = [](ImGuiInputTextCallbackData *d) -> int {
        auto *self = static_cast<Editor *>(d->UserData);
        std::string replacement;
        if (d->EventFlag == ImGuiInputTextFlags_CallbackCompletion) {
          const std::string prefix(d->Buf, d->BufTextLen);
          for (const auto &candidate : self->completion)
            if (candidate.starts_with(prefix)) {
              replacement = candidate;
              break;
            }
        } else if (d->EventFlag == ImGuiInputTextFlags_CallbackHistory) {
          if (d->EventKey == ImGuiKey_UpArrow && self->history_at > 0)
            --self->history_at;
          if (d->EventKey == ImGuiKey_DownArrow &&
              self->history_at + 1 < int(self->history.size()))
            ++self->history_at;
          if (self->history_at < int(self->history.size()))
            replacement = self->history[self->history_at];
        }
        if (!replacement.empty()) {
          d->DeleteChars(0, d->BufTextLen);
          d->InsertChars(0, replacement.c_str());
        }
        return 0;
      };
      if (terminal_open && terminal_focus) {
        ImGui::SetWindowFocus();
        ImGui::SetKeyboardFocusHere();
      }
      if (ImGui::InputText("Command", command, sizeof command,
                           ImGuiInputTextFlags_EnterReturnsTrue |
                               ImGuiInputTextFlags_CallbackCompletion |
                               ImGuiInputTextFlags_CallbackHistory,
                           callback, this)) {
        execute(r, w, c);
        terminal_focus = true;
      }
      if (ImGui::IsItemActive())
        terminal_focus = false;
      ImGui::End();
    }
    if (!open)
      return;
    // Screen-space transform gizmo: select a prop marker, drag its X/Z handles.
    auto *draw = ImGui::GetBackgroundDrawList();
    for (auto &p : r.editing)
      if (p.kind == 1) {
        float xyz[3]{};
        for (size_t i = 0; i < r.editing.size(); ++i)
          if (r.editing[i].target == p.target && r.editing[i].kind >= 1 &&
              r.editing[i].kind <= 3)
            xyz[r.editing[i].kind - 1] = draft[i];
        auto q = orbit.project({xyz[0], xyz[1], xyz[2]}, width, height);
        if (q[2] <= .1f)
          continue;
        ImVec2 center(q[0], q[1]);
        draw->AddCircle(center, 10, IM_COL32(255, 210, 50, 255));
        auto mouse = ImGui::GetMousePos();
        if (!ImGui::GetIO().WantCaptureMouse && ImGui::IsMouseClicked(0) &&
            std::hypot(mouse.x - center.x, mouse.y - center.y) < 15)
          selected = p.target;
        if (selected == int(p.target)) {
          draw->AddLine(center, ImVec2(center.x + 50, center.y),
                        IM_COL32(255, 80, 80, 255), 3);
          draw->AddLine(center, ImVec2(center.x, center.y - 50),
                        IM_COL32(80, 150, 255, 255), 3);
          if (!ImGui::GetIO().WantCaptureMouse && ImGui::IsMouseDragging(0) &&
              std::hypot(mouse.x - center.x, mouse.y - center.y) < 65) {
            checkpoint();
            for (size_t i = 0; i < r.editing.size(); ++i)
              if (r.editing[i].target == p.target) {
                if (r.editing[i].kind == 1)
                  draft[i] =
                      std::clamp(draft[i] + ImGui::GetIO().MouseDelta.x * .02f,
                                 -1000.f, 1000.f);
                if (r.editing[i].kind == 3)
                  draft[i] =
                      std::clamp(draft[i] + ImGui::GetIO().MouseDelta.y * .02f,
                                 -1000.f, 1000.f);
              }
          }
        }
      }
  }
};
} // namespace n3e
