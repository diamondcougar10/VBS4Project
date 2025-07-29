brep_open world [lindex $argv 0]

world nodeapply f {
    f set @vbsblue_instanced_object 1
}
world save [lindex $argv 1]
