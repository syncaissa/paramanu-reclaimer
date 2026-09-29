--[[ docx-filter.lua -- make pandoc's Word output match the LaTeX/PDF layout.

Numbers sections, theorems, equations, tables, figures and the algorithm the
way LaTeX does, maps the paper's custom environments to the Word styles built
by make_reference_docx.py, and swaps PDF figures for their PNG renders.
Run from paper/tools (so pandoc does not read paramanu.sty):
  pandoc ../paramanu_paper.tex --lua-filter docx-filter.lua --citeproc ...
]]

local stringify = pandoc.utils.stringify
local PAPER = "../"

local labels = {}            -- LaTeX label -> number string
local sec = {0, 0, 0}
local thm = {}               -- per-environment counters, reset each section
local eqn, tabn, fign, algn = 0, 0, 0, 0

local THEOREMS = { definition = "Definition", proposition = "Proposition" }
local STYLE = {
  ptitle = "Paper Title", psubtitle = "Paper Subtitle", pauthor = "Paper Author",
  pdate = "Paper Date", pkeywords = "Keywords", pclosing = "Closing",
  definition = "Theorem", proposition = "Theorem", remark = "Theorem", proof = "Proof",
}

local function styled(style, blocks)
  return pandoc.Div(blocks, pandoc.Attr("", {}, {["custom-style"] = style}))
end

local function ooxml(x) return pandoc.RawInline("openxml", x) end
local TAB = '<w:r><w:tab/></w:r>'
local PAGEBREAK = pandoc.RawBlock("openxml", '<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

local function pdf_width_in(path)
  local h = io.popen('pdfinfo "' .. path .. '" 2>/dev/null')
  if not h then return nil end
  local out = h:read("*a"); h:close()
  local w = out:match("Page size:%s*([%d%.]+)")
  -- never wider than the 451pt text block (LaTeX scales these to \textwidth)
  return w and math.min(tonumber(w) / 72, 451 / 72) or nil
end

local function strip_label(tex)
  local lab = tex:match("\\label%{([^}]*)%}")
  return lab, (tex:gsub("\\label%b{}%s*", ""))
end

--------------------------------------------------------------------------
-- Pass 1: number everything in document order (like LaTeX)
--------------------------------------------------------------------------
local function number_pass(doc)
  return doc:walk({
    traverse = "topdown",
    Header = function(h)
      if h.classes:includes("unnumbered") or h.level > #sec then return nil end  -- \\paragraph: unnumbered, as in LaTeX
      local l = h.level
      sec[l] = sec[l] + 1
      for i = l + 1, #sec do sec[i] = 0 end
      if l == 1 then thm = {} end
      local parts = {}
      for i = 1, l do parts[#parts + 1] = tostring(sec[i]) end
      local num = table.concat(parts, ".")
      if h.identifier ~= "" then labels[h.identifier] = num end
      h.content:insert(1, pandoc.Str(num .. "\u{2003}"))
      return h
    end,
    Div = function(d)
      local cls = d.classes[1]
      if THEOREMS[cls] then
        thm[cls] = (thm[cls] or 0) + 1
        local num = sec[1] .. "." .. thm[cls]
        if d.identifier ~= "" then labels[d.identifier] = num end
        local first = d.content[1]
        if first and first.t == "Para" and first.content[1] and first.content[1].t == "Strong" then
          first.content[1] = pandoc.Strong({pandoc.Str(THEOREMS[cls] .. " " .. num)})
        end
        return d
      elseif cls == "algorithm" then
        algn = algn + 1
        labels["alg:batch"] = tostring(algn)
      elseif d.identifier:match("^tab:") then
        tabn = tabn + 1
        labels[d.identifier] = tostring(tabn)
        return d:walk({ Table = function(t)
          local cap = t.caption.long
          if cap[1] then cap[1].content:insert(1, pandoc.Str("Table " .. tabn .. ": ")) end
          return t
        end })
      end
    end,
    Figure = function(f)
      fign = fign + 1
      if f.identifier ~= "" then labels[f.identifier] = tostring(fign) end
      local cap = f.caption.long
      if cap[1] then cap[1].content:insert(1, pandoc.Str("Figure " .. fign .. ": ")) end
      return f
    end,
    Math = function(m)
      if m.mathtype == "DisplayMath" then
        local lab = strip_label(m.text)
        if lab then eqn = eqn + 1; labels[lab] = tostring(eqn) end
      end
    end,
  })
end

--------------------------------------------------------------------------
-- Pass 2: styles, equations, figures, references
--------------------------------------------------------------------------
local eq_seen = 0

-- split a paragraph around display maths; each equation gets its own
-- centred paragraph with a right-aligned number, like \begin{equation}
-- display maths inside italic theorem text: lift it out of the Emph so the
-- paragraph can be split (the surrounding words stay italic)
local function lift_math_from_emph(inlines)
  local out = pandoc.Inlines({})
  for _, il in ipairs(inlines) do
    local lifted = false
    if il.t == "Emph" then
      for _, x in ipairs(il.content) do
        if x.t == "Math" and x.mathtype == "DisplayMath" then lifted = true end
      end
    end
    if lifted then
      local run = pandoc.Inlines({})
      for _, x in ipairs(il.content) do
        if x.t == "Math" and x.mathtype == "DisplayMath" then
          if #run > 0 then out:insert(pandoc.Emph(run)); run = pandoc.Inlines({}) end
          out:insert(x)
        else run:insert(x) end
      end
      if #run > 0 then out:insert(pandoc.Emph(run)) end
    else out:insert(il) end
  end
  return out
end

local function split_display_math(p)
  p.content = lift_math_from_emph(p.content)
  local has = false
  for _, il in ipairs(p.content) do
    if il.t == "Math" and il.mathtype == "DisplayMath" then has = true end
  end
  if not has then return nil end
  local out, buf, after_eq = {}, pandoc.Inlines({}), false
  local function flush()
    -- trim leading/trailing spaces
    while #buf > 0 and (buf[1].t == "Space" or buf[1].t == "SoftBreak") do buf:remove(1) end
    while #buf > 0 and (buf[#buf].t == "Space" or buf[#buf].t == "SoftBreak") do buf:remove(#buf) end
    if #buf > 0 then
      local para = pandoc.Para(buf)
      if after_eq then out[#out + 1] = styled("First Paragraph", {para}) else out[#out + 1] = para end
    end
    buf = pandoc.Inlines({})
  end
  for _, il in ipairs(p.content) do
    if il.t == "Math" and il.mathtype == "DisplayMath" then
      flush()
      local lab, tex = strip_label(il.text)
      local inl = { ooxml(TAB), pandoc.Math("InlineMath", "\\displaystyle " .. tex) }
      if lab then
        inl[#inl + 1] = ooxml(TAB)
        inl[#inl + 1] = pandoc.Str("(" .. labels[lab] .. ")")
      end
      out[#out + 1] = styled("Equation", {pandoc.Para(inl)})
      after_eq = true
    else
      buf:insert(il)
    end
  end
  flush()
  return out
end

-- visual length: capitals are ~45% wider than an average character
local function vis(s)
  local _, caps = s:gsub("%u", "")
  return (utf8.len(s) or #s) + 0.45 * caps
end

-- LaTeX tables take their natural width; approximate that from cell text
local function natural_widths(tbl)
  local ncol = #tbl.colspecs
  for _, cs in ipairs(tbl.colspecs) do
    if cs[2] ~= nil and cs[2] ~= pandoc.ColWidthDefault and cs[2] ~= "ColWidthDefault" then return tbl end
  end
  local maxc, maxw = {}, {}
  for i = 1, ncol do maxc[i] = 2; maxw[i] = 2 end
  local function scan(rows, is_head)
    for _, row in ipairs(rows) do
      for i, cell in ipairs(row.cells) do
        if cell.col_span == 1 and i <= ncol then
          local s = stringify(cell.contents):gsub("\\%a+", ""):gsub("[{}_^$]", "")
          local bold = 1
          pandoc.Blocks(cell.contents):walk({ Strong = function() bold = 1.25 end })
          local n = vis(s) * bold
          if n > maxc[i] then maxc[i] = n end
          for word in s:gmatch("%S+") do
            local k = vis(word) * bold
            if k > maxw[i] then maxw[i] = k end
          end
        end
      end
    end
  end
  scan(tbl.head.rows, true)
  for _, body in ipairs(tbl.bodies) do scan(body.body) end
  -- full = one line per cell; floor = longest word (never split a word)
  local CH, PAD, TW = 6.0, 13, 451
  local full, floor, sf, sw = {}, {}, 0, 0
  for i = 1, ncol do
    full[i] = maxc[i] * CH + PAD; floor[i] = maxw[i] * CH + PAD
    sf = sf + full[i]; sw = sw + floor[i]
  end
  local w = {}
  if sf <= TW then
    for i = 1, ncol do w[i] = full[i] end
  elseif sw >= TW then
    for i = 1, ncol do w[i] = floor[i] * TW / sw end
  else
    local k = (TW - sw) / (sf - sw)
    for i = 1, ncol do w[i] = floor[i] + (full[i] - floor[i]) * k end
  end
  for i = 1, ncol do tbl.colspecs[i] = {tbl.colspecs[i][1], w[i] / TW} end
  return tbl
end

local function transform(doc)
  local blocks = doc:walk({
    Para = function(p) return split_display_math(p) end,
    Table = function(t) return natural_widths(t) end,
    Cite = function(c)
      return pandoc.Span({c}, pandoc.Attr("", {}, {["custom-style"] = "Citation Char"}))
    end,
    Link = function(l)
      local ref = l.attributes["reference"]
      if ref then
        local txt = labels[ref] or stringify(l.content)
        l.content = { pandoc.Span({pandoc.Str(txt)}, pandoc.Attr("", {}, {["custom-style"] = "Ref Char"})) }
        return l
      end
    end,
    Figure = function(f)
      f.content = f.content:walk({ Image = function(img)
        local pdf = PAPER .. img.src
        img.src = (PAPER .. img.src):gsub("%.pdf$", ".png")
        local w = pdf_width_in(pdf)
        if w then img.attributes["width"] = string.format("%.3fin", w) end
        return img
      end })
      return f
    end,
    Div = function(d)
      local cls = d.classes[1]
      if cls == "keyinsight" then
        return {
          styled("Key Insight Title", {pandoc.Para({pandoc.Str("Key Insight")})}),
          styled("Key Insight Body", d.content),
        }
      elseif cls == "execsummary" then
        return {
          styled("Key Insight Title", {pandoc.Para({pandoc.Str("Executive"), pandoc.Space(), pandoc.Str("Summary")})}),
          styled("Key Insight Body", d.content),
        }
      elseif cls == "pabstract" then
        local out = { styled("Abstract Heading", {pandoc.Para({pandoc.Str("Abstract")})}) }
        local body = {}
        for _, b in ipairs(d.content) do
          if b.t == "Div" then out[#out + 1] = styled("Abstract Text", body); body = {}; out[#out + 1] = b
          else body[#body + 1] = b end
        end
        if #body > 0 then out[#out + 1] = styled("Abstract Text", body) end
        out[#out + 1] = PAGEBREAK
        return out
      elseif cls == "algorithm" then
        local png = PAPER .. "figures/alg_batch.png"
        local w = pdf_width_in(PAPER .. "figures/alg_batch.pdf")
        local img = pandoc.Image({}, png, "", pandoc.Attr("", {}, w and {width = string.format("%.3fin", w)} or {}))
        return styled("Algorithm", {pandoc.Para({img})})
      elseif cls == "pclosing" then
        return {
          pandoc.Header(1, {pandoc.Str("References")}, pandoc.Attr("references", {"unnumbered"})),
          pandoc.Div({}, pandoc.Attr("refs")),
          styled("Closing", d.content),
        }
      elseif STYLE[cls] then
        d.attributes["custom-style"] = STYLE[cls]
        return d
      end
    end,
  })
  return blocks
end

function Pandoc(doc)
  doc = number_pass(doc)
  doc = transform(doc)
  return doc
end
