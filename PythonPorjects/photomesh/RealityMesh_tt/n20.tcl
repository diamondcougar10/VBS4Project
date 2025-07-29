# Open input file.
tav_open world [lindex $argv 0]

world arealapply a {
    a del -all *
}

world linearapply l {
	l del -all *
}

world pointapply p {
    p del -all *
}

set vertex_list_xyz {}

world vertexapply v {

	set coords [v coordinates]

	set index [lsearch -sorted -increasing -exact $vertex_list_xyz $coords]

	if {$index != -1} {
		#duplicate point
		continue
	}

	world new_point -vertex_index [v index] p
	p set -int "tsg_point" 1
	
	lappend vertex_list_xyz $coords
	set vertex_list_xyz [lsort -unique -increasing $vertex_list_xyz]
}

# Save to output file.
world save -remove_unattributed [lindex $argv 1]