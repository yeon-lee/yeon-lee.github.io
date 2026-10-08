---
layout: page
permalink: /quantum-computing/
title: Quantum Computing
description: error-corrected quantum computers with far fewer qubits, and where the field stands
nav: true
nav_order: 1.5
og_image: /assets/img/qc/quantum-computing-card.png
---

<!--
  _pages/quantum-computing.md: the Quantum Computing tab. Edit the text here.
  Figures come from _includes/qc/, with data in _data/qc_codes.yml (top
  figure), _data/qc_estimates.yml (qubit-estimate chart),
  _data/qc_architecture.yml (blueprint) and _data/qc_timeline.yml
  (milestones); assets/js/quantum-computing.js draws them. The four
  <section class="topic"> blocks collapse like the research page, and the
  "Our work" links in the blueprint open the section with the matching id.
  Styles: _sass/_quantum-computing.scss.
-->

Quantum computers make errors constantly, so a machine that runs long, useful programs has to correct its own mistakes as it computes. The leading approach is expensive: each reliable *logical* qubit is built from hundreds to thousands of noisy *physical* qubits. Our group designs error-correcting codes that store many logical qubits in far fewer physical ones, and works out how to compute with them.
{: .qc-lede}

{% include qc/budget.liquid %}

There is a catch. Packed this tightly, logical qubits overlap on the same physical qubits, so acting on one without disturbing the others becomes the hard part. Much of our recent work is about that catch.

## How many qubits does a useful quantum computer need?

The field's standard yardstick is factoring a 2048-bit RSA number with Shor's algorithm. Published estimates have fallen from about a billion physical qubits in 2012 to under 100,000 today, or about 13,000 for a machine willing to run for decades. The two most recent drops, both in 2026, came from replacing the surface code with high-rate quantum LDPC codes, the family of codes we design.

{% include qc/estimates.liquid %}

These are designs on paper: no machine this large exists yet, and runtimes range from hours to decades. Still, the trend is why high-rate codes have moved from theory papers into company roadmaps.

## Inside a fault-tolerant quantum computer

A fault-tolerant quantum computer is several machines working together. The blueprint shows the main parts of a design built on high-rate codes, how far the field has come on each, and what is still open. Parts where our group contributes are tagged.

{% include qc/blueprint.liquid %}

## Our work in detail

<p class="qc-hint">Select a heading to expand it, or <a href="#" data-qc-topics-all>show all</a>.</p>

<section class="topic" id="codes" style="--tint: #d9473b" markdown="1">
<h2>Error-correcting codes</h2>
<div class="topic-body" markdown="1">

The surface code stores one logical qubit per patch, and each patch grows with the square of the distance. High-rate quantum LDPC codes break that pattern: each check still involves only a handful of qubits, but checks can reach across the block, so one block can hold dozens or hundreds of logical qubits. The hard part is that block size, encoding rate, distance and check weight all pull against each other.

- [Design principles for ultra-high-rate quantum codes](https://arxiv.org/abs/2609.30069) (2026, with Koki Okada, Nishad Maskara, Kenta Kasai and Hengyun Zhou) turns these trade-offs into design rules. One finding: at a realistic 0.1% physical error rate, heavier checks are often worth it, because they buy larger distance in a small block. The resulting codes, such as [[90,21,11]], [[140,31,15]] and [[200,43,20]], need only a few data qubits per logical qubit.
- [Designing group-valued codes](https://arxiv.org/abs/2610.06820) (2026) builds codes such as [[1088,128,22]] and [[1024,256,24]] with a complete, regular basis of logical operators about as light as the distance allows, and shows why this is impossible for a common class of codes built on odd-order groups.
- [Lifting lifted-product codes](https://arxiv.org/abs/2607.28621) (2026, with Yuta Hirasaki) grows a code into a family that keeps its local structure. It finds codes with better parameters than previously reported, and takes a first step toward code families with a well-defined large-size limit.

</div>
</section>

<section class="topic" id="logic" style="--tint: #d9473b" markdown="1">
<h2>Logical operations</h2>
<div class="topic-body" markdown="1">

Packing many logical qubits into one block creates a new problem. To compute, you need to know where each logical qubit lives, how it is labeled, and how to act on it without disturbing its neighbors. For Abelian lifted-product codes, which include many of the best high-rate designs, the row-reduction shortcut that works for simpler product codes can fail.

- [Logical spectroscopy](https://arxiv.org/abs/2607.05386) (2026) fixes this for Abelian lifted-product codes. Like a prism splitting light into colors, it splits the code's algebra into small independent pieces, solves each one, and reassembles a complete, labeled set of logical operators. It has been applied to codes with up to 5,000 physical qubits.
- [Full regular low-weight bases](https://arxiv.org/abs/2610.06820) (2026) introduces the *frame width*: the smallest weight limit that still allows a complete canonical set of logical operators. Lighter operators make logical operations cheaper, so frame width belongs next to distance in resource estimates.
- [Lifting lifted-product codes](https://arxiv.org/abs/2607.28621) (2026, with Ph.D. student Yuta Hirasaki) shows that surgery gadgets, the standard way to measure logical qubits, carry over across a family of codes, sometimes at lower cost.

Next, with support from a [Microsoft Quantum Pioneers award](https://quantum.microsoft.com/en-us/insights/blogs/announcing-latest-winners-and-finalists-of-the-quantum-pioneers-program), we are building on logical spectroscopy toward hardware-aware compilation for qLDPC codes.

</div>
</section>

<section class="topic" id="hardware" style="--tint: #d9473b" markdown="1">
<h2>Hardware and dynamics</h2>
<div class="topic-body" markdown="1">

Codes have to run on real machines, and real machines suggest new codes.

- [Two qubits per atom](https://doi.org/10.1038/s41534-024-00898-7) (npj Quantum Information 2024): with Jacob Covey's group at Illinois, an architecture that stores two qubits in each ytterbium-171 atom, so error correction needs fewer two-atom gates.
- [Stable Floquet codes](https://doi.org/10.1103/PhysRevLett.132.070401) (Phys. Rev. Lett. 2024): Floquet codes protect qubits with a repeating cycle of simple two-qubit measurements. We showed that the dynamical topological order they create survives perturbations.
- [Decoding measurement-prepared states](https://arxiv.org/abs/2208.11699) (2022): measurements can create long-range entangled states quickly, and the outcomes can be decoded by classical computation instead of repeating the experiment exponentially many times.

</div>
</section>

<section class="topic" id="limits" style="--tint: #d9473b" markdown="1">
<h2>Noise and thresholds</h2>
<div class="topic-body" markdown="1">

Code families typically have an error threshold: below a certain noise level, bigger codes protect better; above it, no decoder can recover the information. We study thresholds as phase transitions, like water freezing, using information-theoretic quantities that do not depend on any particular decoder. This connects to our broader work on [mixed-state phases of matter](/research/#information).

- [Exact coherent information for the toric code](https://doi.org/10.1103/hlfh-86yz) (Phys. Rev. Lett. 2025) gives the first exact formula for how much information survives noise, tying the code's fundamental threshold to the random-bond Ising model. A [follow-up](https://doi.org/10.1103/PhysRevA.111.032402) (Phys. Rev. A 2025, with Ryotaro Niwa) extends this to all CSS codes.
- [Hierarchy of Rényi coherent information](https://arxiv.org/abs/2609.11930) (2026, with Ph.D. student Akash Vijay and Luis Colmenarez) proves that, for independent Pauli noise, the computable Rényi versions used across the field are ordered by their Rényi index, and gives them an operational meaning.
- [Information critical phases](https://arxiv.org/abs/2512.22121) (2025, with Akash Vijay) finds, in noisy Z<sub>N</sub> toric codes with N > 4, a whole intermediate phase in which a fraction of the stored information survives.
- Beyond standard codes: [error thresholds of SYK codes](https://doi.org/10.1103/srf2-1f6d) (Phys. Rev. B 2026, with Jaewon Kim and Ehud Altman) and [approximate error correction at chiral topological edges](https://arxiv.org/abs/2608.06258) (2026, with former postdoc Bowen Shi).

</div>
</section>

## Milestones

Selected results in theory, architecture and experiment, newest first, with our group's work marked.

{% include qc/timeline.liquid %}

## Key terms

<dl class="qc-terms">
<div><dt>Physical qubit</dt><dd>One quantum bit in hardware: an atom, an ion or a superconducting circuit. Each one makes errors.</dd></div>
<div><dt>Logical qubit</dt><dd>One qubit's worth of information spread over many physical qubits, so that errors can be detected and undone.</dd></div>
<div><dt>Code distance <i>d</i></dt><dd>The smallest number of single-qubit errors that can change the stored information without being detected. A code of distance <i>d</i> corrects any (<i>d</i> − 1)/2 errors, rounded down.</dd></div>
<div><dt>[[<i>n</i>, <i>k</i>, <i>d</i>]]</dt><dd>Shorthand for a code that stores <i>k</i> logical qubits in <i>n</i> physical qubits at distance <i>d</i>. A surface-code patch is [[<i>d</i>², 1, <i>d</i>]].</dd></div>
<div><dt>Encoding rate</dt><dd>Logical qubits per data qubit, <i>k</i>/<i>n</i>: 1/121 for a distance-11 surface code, 21/90 for our [[90,21,11]] code.</dd></div>
<div><dt>qLDPC code</dt><dd>Quantum low-density parity-check code. Each check involves only a few qubits and each qubit only a few checks, but checks may connect distant qubits.</dd></div>
<div><dt>Check weight</dt><dd>How many qubits one check involves: 4 in the surface code, 6 to 10 in the high-rate codes on this page.</dd></div>
<div><dt>Threshold</dt><dd>For a family of codes, the physical error rate below which making the code bigger makes it better.</dd></div>
<div><dt>Decoder</dt><dd>The classical algorithm that reads the check results and infers a correction. In a real machine it has to keep up with the stream of results.</dd></div>
<div><dt>Code surgery</dt><dd>Measuring logical qubits by temporarily attaching extra qubits and checks to a code; a leading way to compute with qLDPC codes.</dd></div>
<div><dt>Magic state</dt><dd>A special resource state that, combined with the easy operations, makes a quantum computer universal.</dd></div>
</dl>

## Get involved

Talks from [QID 2026: qLDPC Theory and Application](https://symposia.kias.re.kr/QID2026), the workshop we co-organized at KIAS in Seoul in July 2026, are on the [KIAS School of Physics YouTube channel](https://www.youtube.com/@schoolofphysicskias6537). Students and postdocs who want to work on these questions can start at the [Join](/join/) page.

<script defer src="{{ '/assets/js/quantum-computing.js' | relative_url }}"></script>
