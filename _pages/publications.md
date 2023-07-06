---
layout: page
permalink: /publications/
title: Publications
# description: publications by categories in reversed chronological order.
years: [2015,2016,2018,2019,2020,2021,2022]
nav: false
nav_order: 9
---
<!-- _pages/publications.md -->
<div class="publications">

{%- for y in page.years reversed  %}
  <h2 class="year">{{y}}</h2>
  {% bibliography -f papers -q @*[year={{y}}]* %}
{% endfor %}

</div>
