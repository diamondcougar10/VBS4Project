tav_open world [lindex $argv 0]

world arealapply a {
	if {[a has num_tris]} {
		if {[a get num_tris] <= 500000} {
			a del -all *
		}
	} else {
		a del -all *
	}
}

# Save to output file.
world save -remove_unattributed [lindex $argv 1]
