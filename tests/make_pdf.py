"""Synthetic journal-style PDFs with a known text, for the tests."""
import io

import fitz

ARTICLE = [
 ("h", "1. Introduction"),
 ("p", "Flood frequency analysis in ungauged basins remains a central problem in hydrology<sup>1,2</sup>. Regional methods transfer information from gauged sites to ungauged ones, e.g. by regression on basin descriptors (Jalbert et al., 2022; Smith and Jones, 2019). The index-flood method assumes that the flood distribution is identical across a homogeneous region, up to a scale factor."),
 ("h3", "1.1 IDF Curves"),
 ("p", "Intensity-duration-frequency curves summarise how rainfall intensity varies with duration and return period. They are the main design tool for urban drainage."),
 ("p", "In this study, we define the specific discharge as"),
 ("eq", "I = Q / D"),
 ("p", "where Q = discharge and D = drainage area."),
 ("p", "The approach has been criticised because it ignores spatial dependence between stations (see Hosking and Wallis, 1997, for a detailed discussion of the regional L-moment algorithm and its assumptions). Nevertheless, it remains widely used in operational practice across Canada and Europe, where more than 1,200 stations are monitored continuously."),
 ("h", "2. Data and methods"),
 ("h2", "2.1. Study area"),
 ("p", "The study area covers 84 basins in southern Quebec, ranging from 12 to 6,800 km² in drainage area. Annual maximum discharges were extracted from the national hydrometric archive for the period 1960–2020. Stations with fewer than 20 years of record were excluded, which left 71 stations for the analysis."),
 ("p", "Each station was assigned to one of three regions (n = 24, 26 and 21) based on physiographic similarity. Mean annual precipitation varies between 900 and 1,300 mm across the domain, with a pronounced snowmelt contribution in spring."),
 ("fig", "Figure 1. Location of the 71 hydrometric stations used in the analysis."),
 ("h2", "2.2. Statistical model"),
 ("p", "We fitted a generalized extreme value distribution to the annual maxima at each site. The location parameter was modelled as a linear function of the logarithm of drainage area, while the scale and shape parameters were held constant within each region. Parameters were estimated by maximum likelihood using a Bayesian framework with weakly informative priors."),
 ("p", "Model adequacy was assessed with probability plots and the Anderson–Darling statistic. A leave-one-out cross-validation was used to evaluate predictive performance at ungauged sites, following the procedure described in earlier work<sup>3</sup>."),
 ("h", "3. Results"),
 ("p", "The regional model reproduced the observed 100-year flood with a median relative error of 14 %. Errors were largest for small basins, where local storage effects dominate the flood response. The shape parameter was estimated at −0.08 in region A, which indicates a slightly heavy upper tail."),
 ("tab", "Table 1. Cross-validation scores for the three regions."),
 ("p", "Table 1 shows that errors decrease with drainage area in all three regions. The largest observed peak reached 850 m<sup>3</sup> s<sup>−1</sup> in 1998."),
 ("p", "Performance was comparable between regions, although region C showed a systematic underestimation of large floods. This bias disappeared when the snow water equivalent was added as a covariate, suggesting that snowmelt processes explain a substantial part of the residual variability."),
 ("h", "4. Discussion"),
 ("p", "Our results confirm that a simple scaling with drainage area captures most of the spatial variability in flood magnitude. However, the approach should be used with caution in basins with large lakes or reservoirs, where attenuation strongly modifies the flood peak. Future work should incorporate climate projections to assess non-stationarity in flood regimes over the coming decades."),
 ("h", "5. Conclusions"),
 ("p", "We proposed a Bayesian regional model for flood quantiles in southern Quebec. The model is parsimonious, easy to interpret and performs well in cross-validation. It provides a practical tool for engineers who design infrastructure in ungauged basins."),
 ("h", "References"),
 ("ref", "Hosking, J.R.M., Wallis, J.R., 1997. Regional Frequency Analysis. Cambridge University Press."),
 ("ref", "Jalbert, J., Genest, C., Perreault, L., 2022. Interpolation of precipitation extremes on a large domain. Journal of Hydrology 612, 128123."),
]


def two_column_article(repeat=1, columns=2):
    """Return an open fitz document laid out like a journal article."""
    css = "p{font-family:serif;font-size:9.5pt;text-align:justify;margin:0 0 6pt 0;} h1{font-family:sans-serif;font-size:10pt;font-weight:bold;margin:8pt 0 4pt 0} h2{font-family:sans-serif;font-size:9.5pt;font-style:italic;font-weight:bold;margin:6pt 0 3pt 0} .eq{text-align:center;font-style:italic} .cap{font-size:8pt} .sub{font-style:italic;margin:6pt 0 3pt 0}"
    html = []
    for k, t in ARTICLE:
        if k == "h": html.append(f"<h1>{t}</h1>")
        elif k == "h2": html.append(f"<h2>{t}</h2>")
        elif k == "h3": html.append(f"<p class='sub'>{t}</p>")
        elif k == "eq": html.append(f"<p class='eq'>{t}</p>")
        elif k in ("fig", "tab"): html.append(f"<p class='cap'>{t}</p>")
        else: html.append(f"<p>{t}</p>")
    story = fitz.Story(html="".join(html) * repeat, user_css=css)
    W, H = fitz.paper_size("letter")
    cols = ([fitz.Rect(54, 70, 298, H - 60), fitz.Rect(314, 70, W - 54, H - 60)] if columns == 2
            else [fitz.Rect(72, 70, W - 72, H - 60)])
    buf = io.BytesIO(); wr = fitz.DocumentWriter(buf)
    more = 1
    while more:
        dev = wr.begin_page(fitz.Rect(0, 0, W, H))
        for r in cols:
            more, _ = story.place(r); story.draw(dev)
            if not more: break
        wr.end_page()
    wr.close()
    doc = fitz.open("pdf", buf.getvalue())
    for i, p in enumerate(doc):
        p.insert_text((54, 40), "Journal of Hydrology 612 (2022) 128123", fontsize=8)
        p.insert_text((W / 2 - 4, H - 30), str(i + 1), fontsize=8)
    return doc


def glued_heading_page():
    """A plain-text subsection title sitting in the same block as its paragraph."""
    doc = fitz.open()
    page = doc.new_page()
    text = ("1.1 IDF Curves\n"
            "Intensity-duration-frequency curves summarise how rainfall intensity varies with\n"
            "duration and return period. They are the main design tool for urban drainage and\n"
            "are updated regularly by national agencies.")
    page.insert_textbox(fitz.Rect(72, 72, 540, 200), text, fontsize=10, fontname="tiro")
    return doc
